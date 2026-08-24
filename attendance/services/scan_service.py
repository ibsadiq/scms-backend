from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from attendance.models import AttendanceDevice, AttendanceEvent, AttendanceScan
from idcards.models import IDCard, RFIDCredential
from idcards.services import RFIDCredentialService
from .attendance_policy_service import AttendancePolicyService
from .staff_attendance_service import StaffAttendanceService
from .student_attendance_service import StudentAttendanceService
from .security_service import DeviceSecurityEventService
from attendance.models import DeviceSecurityEvent


class AttendanceScanService:
    MAX_FUTURE = timedelta(minutes=5)
    MAX_PAST = timedelta(days=7)

    @classmethod
    def _direction(cls, device, supplied):
        if device.mode == AttendanceDevice.Mode.ENTRY:
            return AttendanceScan.Direction.ENTRY
        if device.mode == AttendanceDevice.Mode.EXIT:
            return AttendanceScan.Direction.EXIT
        return supplied if supplied in AttendanceScan.Direction.values else None

    @classmethod
    def process(cls, *, device, uid, scanned_at, request_id, direction="", metadata=None):
        try:
            normalized = RFIDCredentialService.normalize_uid(uid)
        except Exception:
            normalized = str(uid or "").strip().upper()[:64]
        resolved_direction = cls._direction(device, direction)
        scan = AttendanceScan.objects.create(
            device=device, raw_uid=normalized, request_id=request_id, scanned_at=scanned_at,
            direction=resolved_direction or "", metadata=metadata or {},
        )
        try:
            return cls._interpret(scan, normalized, resolved_direction)
        except Exception as exc:
            scan.result = AttendanceScan.Result.ERROR
            scan.processing_error = str(exc)[:500]
            scan.processed_at = timezone.now()
            scan.save(update_fields=("result", "processing_error", "processed_at"))
            return scan

    @classmethod
    @transaction.atomic
    def _interpret(cls, scan, normalized_uid, direction):
        now = timezone.now()
        policy = AttendancePolicyService.get_current()
        if not scan.device.is_active:
            DeviceSecurityEventService.record(
                device=scan.device, event_type=DeviceSecurityEvent.EventType.DISABLED_DEVICE,
                severity=DeviceSecurityEvent.Severity.WARNING, request_id=scan.request_id,
            )
            return cls._finish(scan, AttendanceScan.Result.INACTIVE_DEVICE)
        if not policy.device_attendance_enabled:
            return cls._finish(scan, AttendanceScan.Result.RFID_DISABLED)
        if scan.scanned_at > now + cls.MAX_FUTURE or scan.scanned_at < now - cls.MAX_PAST:
            return cls._finish(scan, AttendanceScan.Result.INVALID_TIMESTAMP)
        if not direction:
            return cls._finish(scan, AttendanceScan.Result.INVALID_DIRECTION)
        try:
            _, credential = RFIDCredentialService.resolve(normalized_uid)
        except Exception:
            credential = None
        if credential is None:
            return cls._finish(scan, AttendanceScan.Result.UNKNOWN_CARD)
        # Lock only the credential row. Joining both nullable holder paths here
        # creates outer joins, which PostgreSQL cannot include in FOR UPDATE.
        credential = RFIDCredential.objects.select_for_update().get(pk=credential.pk)
        scan.credential = credential
        if credential.status != RFIDCredential.Status.ACTIVE:
            return cls._finish(scan, AttendanceScan.Result.REVOKED_CREDENTIAL)
        card = credential.id_card
        if card.effective_status == "EXPIRED":
            return cls._finish(scan, AttendanceScan.Result.EXPIRED_CARD)
        if card.status != IDCard.Status.ACTIVE:
            return cls._finish(scan, AttendanceScan.Result.INACTIVE_CARD)
        holder = card.student or card.staff
        if not holder.is_active:
            return cls._finish(scan, AttendanceScan.Result.INACTIVE_HOLDER)
        window = timedelta(seconds=policy.device_duplicate_window_seconds)
        duplicate = AttendanceScan.objects.filter(
            credential=credential, direction=direction, result=AttendanceScan.Result.SUCCESS,
            scanned_at__gte=scan.scanned_at - window, scanned_at__lte=scan.scanned_at,
        ).exclude(pk=scan.pk).exists()
        if duplicate:
            return cls._finish(scan, AttendanceScan.Result.DUPLICATE)
        event_type = AttendanceEvent.EventType.ENTRY if direction == AttendanceScan.Direction.ENTRY else AttendanceEvent.EventType.EXIT
        event_metadata = {"device_id": scan.device_id, "scan_id": scan.pk}
        if card.student_id:
            attendance = StudentAttendanceService.mark_rfid(
                student=card.student, occurred_at=scan.scanned_at, direction=event_type, metadata=event_metadata
            )
        else:
            attendance = StaffAttendanceService.mark_rfid(
                staff=card.staff, occurred_at=scan.scanned_at, direction=event_type, metadata=event_metadata
            )
        scan.metadata = {**scan.metadata, "attendance_status": attendance.status.name}
        return cls._finish(scan, AttendanceScan.Result.SUCCESS)

    @staticmethod
    def _finish(scan, result):
        scan.result = result
        scan.processed_at = timezone.now()
        scan.save(update_fields=("credential", "result", "processed_at", "metadata"))
        return scan
