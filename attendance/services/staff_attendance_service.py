from django.db import transaction
from academic.models import Staff
from attendance.models import AttendanceEvent, StaffAttendance
from .attendance_event_service import AttendanceEventService
from .attendance_policy_service import AttendancePolicyService
from .attendance_status_service import AttendanceStatusService


class StaffAttendanceService:
    @classmethod
    @transaction.atomic
    def mark_manual(cls, *, staff, attendance_date, status_name, marked_by=None,
                    time_in=None, time_out=None, notes=""):
        staff = Staff.objects.select_for_update().get(pk=staff.pk)
        policy = AttendancePolicyService.get_current()
        normalized = str(status_name).strip().title()
        if normalized == "Present" and time_in and policy.staff_late_after and time_in >= policy.staff_late_after:
            normalized = "Late"
        status = AttendanceStatusService.resolve(normalized)
        current = StaffAttendance.objects.filter(staff=staff, date=attendance_date).first()
        previous = cls._state(current)
        attendance, created = StaffAttendance.objects.update_or_create(
            staff=staff, date=attendance_date,
            defaults={"status": status, "time_in": time_in, "time_out": time_out,
                      "notes": notes, "marked_by": marked_by},
        )
        event_type = (AttendanceEvent.EventType.MARKED_LATE if status.late else
                      AttendanceEvent.EventType.MARKED_ABSENT if status.absent else
                      AttendanceEvent.EventType.MARKED_PRESENT) if created else AttendanceEvent.EventType.MANUAL_CORRECTION
        AttendanceEventService.record(
            staff=staff, source=AttendanceEvent.Source.MANUAL, event_type=event_type,
            performed_by=marked_by, previous_state=previous, new_state=cls._state(attendance),
        )
        return attendance, created

    @staticmethod
    def _state(attendance):
        if not attendance:
            return {}
        return {"status": attendance.status.name,
                "time_in": attendance.time_in.isoformat() if attendance.time_in else None,
                "time_out": attendance.time_out.isoformat() if attendance.time_out else None,
                "notes": attendance.notes}

    @classmethod
    @transaction.atomic
    def mark_rfid(cls, *, staff, occurred_at, direction, metadata=None):
        staff = Staff.objects.select_for_update().get(pk=staff.pk)
        local = occurred_at.astimezone()
        attendance_date, scan_time = local.date(), local.time().replace(tzinfo=None)
        current = StaffAttendance.objects.select_for_update().filter(staff=staff, date=attendance_date).first()
        previous = cls._state(current)
        policy = AttendancePolicyService.get_current()
        status_name = "Late" if direction == AttendanceEvent.EventType.ENTRY and policy.staff_late_after and scan_time > policy.staff_late_after else "Present"
        status = AttendanceStatusService.resolve(status_name)
        if direction == AttendanceEvent.EventType.ENTRY:
            time_in = current.time_in if current and current.time_in else scan_time
            time_out = current.time_out if current else None
        else:
            time_in = current.time_in if current else None
            time_out = scan_time
            if current and not current.status.absent:
                status = current.status
        attendance, _ = StaffAttendance.objects.update_or_create(
            staff=staff, date=attendance_date,
            defaults={
                "status": status, "time_in": time_in, "time_out": time_out,
                "notes": current.notes if current else "", "marked_by": current.marked_by if current else None,
            },
        )
        AttendanceEventService.record(
            staff=staff, source=AttendanceEvent.Source.RFID, event_type=direction,
            occurred_at=occurred_at, previous_state=previous, new_state=cls._state(attendance), metadata=metadata,
        )
        return attendance
