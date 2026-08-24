from datetime import datetime, timedelta, time

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from school.testcases import TenantTestCase
from django_tenants.utils import schema_context
from rest_framework.test import APIRequestFactory, force_authenticate

from academic.models import Staff, Student
from attendance.models import AttendanceDevice, AttendanceEvent, AttendancePolicy, AttendanceScan, StaffAttendance, StudentAttendance
from attendance.services import AttendanceDeviceService, AttendanceScanService, DeviceAuthenticationError, StaffAttendanceService, StudentAttendanceService
from attendance.views_device import AttendanceDeviceViewSet, DeviceScanIngestView
from idcards.models import HolderType, IDCard, IDCardTemplate, RFIDCredential
from idcards.services import CardService, RFIDCredentialService
from tenants.models import Client, TenantStatus


User = get_user_model()
EMPTY_LAYOUT = {"schema_version": 1, "elements": []}


class RFIDFoundationTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        return super().setup_tenant(tenant)

    def setUp(self):
        self.admin = User.objects.create_user(email="rfid-admin@example.com", password="test", is_admin=True, is_staff=True)
        self.teacher = User.objects.create_user(email="rfid-teacher@example.com", password="test", is_teacher=True)
        staff_user = User.objects.create_user(email="rfid-staff@example.com", password="test", first_name="Musa", last_name="Ali")
        self.student = Student.objects.create(first_name="Amina", last_name="Bello", parent_contact="08030000001", admission_number="RFID-STU")
        self.staff = Staff.objects.create(user=staff_user, designation="Guard")
        self.student_template = IDCardTemplate.objects.create(name="RFID Student", holder_type=HolderType.STUDENT, front_layout=EMPTY_LAYOUT, back_layout=EMPTY_LAYOUT)
        self.staff_template = IDCardTemplate.objects.create(name="RFID Staff", holder_type=HolderType.STAFF, front_layout=EMPTY_LAYOUT, back_layout=EMPTY_LAYOUT)
        self.student_card = CardService.issue_student_card(student=self.student, template=self.student_template)
        self.staff_card = CardService.issue_staff_card(staff=self.staff, template=self.staff_template)
        self.student_credential = RFIDCredentialService.assign(id_card=self.student_card, uid="04:A6:27:92")
        self.staff_credential = RFIDCredentialService.assign(id_card=self.staff_card, uid="1122-3344")
        self.device, self.secret = AttendanceDeviceService.register(name="Main Gate", device_identifier="gate-01", mode=AttendanceDevice.Mode.BIDIRECTIONAL)
        self.policy = AttendancePolicy.objects.create(device_attendance_enabled=True)
        self.factory = APIRequestFactory()
        # Keep the largest test offset (+2 hours) safely behind the service's
        # current-time boundary while retaining all relative scan timings.
        self.base = (timezone.now() - timedelta(hours=2, minutes=1)).replace(microsecond=0)

    def scan(self, uid="04A62792", direction="ENTRY", seconds=0, request_id=None, device=None):
        return AttendanceScanService.process(device=device or self.device, uid=uid, scanned_at=self.base + timedelta(seconds=seconds), direction=direction, request_id=request_id or f"request-{AttendanceScan.objects.count()}")

    def authenticate(self, *, secret=None, request_id="auth", identifier="gate-01"):
        timestamp = str(int(timezone.now().timestamp()))
        body = b""
        signature = AttendanceDeviceService.sign_request(
            secret=secret or self.secret, method="POST", path="/api/attendance/device-scans/",
            request_timestamp=timestamp, request_id=request_id, body=body,
        )
        return AttendanceDeviceService.authenticate(
            identifier=identifier, secret=secret or self.secret, request_timestamp=timestamp,
            request_id=request_id, signature=signature, method="POST",
            path="/api/attendance/device-scans/", body=body,
        )

    def test_uid_is_normalized_hashed_and_duplicate_never_reassigned(self):
        self.assertEqual(self.student_credential.uid_last_four, "2792")
        self.assertEqual(len(self.student_credential.uid_hash), 64)
        self.assertNotIn("04A62792", self.student_credential.uid_hash)
        with self.assertRaises(ValidationError):
            RFIDCredentialService.assign(id_card=self.staff_card, uid="04-a6-27-92")

    def test_replacement_retains_history_and_old_uid_is_rejected(self):
        replacement = RFIDCredentialService.replace(self.student_credential, new_uid="AABBCCDD", actor=self.admin, reason="Lost")
        self.student_credential.refresh_from_db()
        self.assertEqual(self.student_credential.status, RFIDCredential.Status.REPLACED)
        self.assertEqual(replacement.status, RFIDCredential.Status.ACTIVE)
        self.assertEqual(RFIDCredential.objects.filter(id_card=self.student_card).count(), 2)
        with self.assertRaises(ValidationError):
            RFIDCredentialService.assign(id_card=self.student_card, uid="04A62792")

    def test_assignment_rejects_inactive_and_expired_cards(self):
        for status, expires_at in [(IDCard.Status.INACTIVE, None), (IDCard.Status.ACTIVE, timezone.now() - timedelta(days=1))]:
            holder = Student.objects.create(
                first_name="Card", last_name="State",
                parent_contact=f"0803999000{1 if status == IDCard.Status.INACTIVE else 2}",
            )
            card = CardService.issue_student_card(student=holder, template=self.student_template)
            card.status, card.expires_at = status, expires_at
            card.save(update_fields=("status", "expires_at"))
            with self.subTest(status=status, expires_at=expires_at), self.assertRaises(ValidationError):
                RFIDCredentialService.assign(id_card=card, uid="AA11BB22" if status == IDCard.Status.INACTIVE else "CC33DD44")

    def test_device_authentication_rotation_and_disable(self):
        authenticated = self.authenticate(request_id="auth-1")
        self.assertEqual(authenticated, self.device)
        new_secret = AttendanceDeviceService.rotate_secret(self.device)
        with self.assertRaises(DeviceAuthenticationError):
            self.authenticate(secret=self.secret, request_id="auth-2")
        self.assertEqual(self.authenticate(secret=new_secret, request_id="auth-3"), self.device)
        self.device.is_active = False
        self.device.save(update_fields=("is_active",))
        self.assertEqual(self.scan(request_id="inactive-device").result, AttendanceScan.Result.INACTIVE_DEVICE)

    def test_device_credentials_are_isolated_by_tenant_schema(self):
        with schema_context("public"):
            other = Client(schema_name="rfid_isolation_school", name="RFID Isolation School", status=TenantStatus.ACTIVE)
            other.auto_create_schema = True
            other.save()
        with schema_context(other.schema_name):
            _, other_secret = AttendanceDeviceService.register(
                name="Other Main Gate", device_identifier="gate-01", mode=AttendanceDevice.Mode.ENTRY
            )
        with self.assertRaises(DeviceAuthenticationError):
            self.authenticate(secret=other_secret, request_id="cross-tenant")
        self.assertEqual(
            self.authenticate(secret=self.secret, request_id="local-tenant"),
            self.device,
        )

    def test_unknown_revoked_and_invalid_direction_scans_are_retained(self):
        unknown = self.scan(uid="DEADBEEF", request_id="unknown")
        RFIDCredentialService.revoke(self.student_credential, actor=self.admin)
        revoked = self.scan(request_id="revoked")
        invalid = self.scan(direction="", request_id="direction")
        self.assertEqual((unknown.result, revoked.result, invalid.result), (AttendanceScan.Result.UNKNOWN_CARD, AttendanceScan.Result.REVOKED_CREDENTIAL, AttendanceScan.Result.INVALID_DIRECTION))
        self.assertEqual(AttendanceScan.objects.count(), 3)
        self.assertIsNone(unknown.credential)

    def test_inactive_revoked_and_expired_cards_never_create_attendance(self):
        cases = [(IDCard.Status.INACTIVE, None, AttendanceScan.Result.INACTIVE_CARD), (IDCard.Status.REVOKED, None, AttendanceScan.Result.INACTIVE_CARD), (IDCard.Status.ACTIVE, timezone.now() - timedelta(minutes=1), AttendanceScan.Result.EXPIRED_CARD)]
        for index, (status, expiry, expected) in enumerate(cases):
            self.student_card.status, self.student_card.expires_at = status, expiry
            self.student_card.save(update_fields=("status", "expires_at"))
            scan = self.scan(request_id=f"card-state-{index}")
            self.assertEqual(scan.result, expected)
        self.assertEqual(StudentAttendance.objects.count(), 0)

    def test_student_entry_exit_first_in_and_latest_out(self):
        first = self.scan(direction="ENTRY", seconds=0)
        later_entry = self.scan(direction="ENTRY", seconds=60)
        first_exit = self.scan(direction="EXIT", seconds=3600)
        last_exit = self.scan(direction="EXIT", seconds=7200)
        row = StudentAttendance.objects.get(student=self.student, date=self.base.date())
        self.assertEqual(first.result, AttendanceScan.Result.SUCCESS)
        self.assertEqual(first.processing_error, "")
        self.assertEqual(later_entry.result, AttendanceScan.Result.SUCCESS)
        self.assertEqual(row.time_in, self.base.time())
        self.assertEqual(row.time_out, (self.base + timedelta(seconds=7200)).time())
        self.assertEqual(AttendanceEvent.objects.filter(student=self.student, source=AttendanceEvent.Source.RFID).count(), 4)

    def test_staff_entry_and_exit_update_daily_attendance(self):
        self.scan(uid="11223344", direction="ENTRY", request_id="staff-in")
        self.scan(uid="11223344", direction="EXIT", seconds=1800, request_id="staff-out")
        row = StaffAttendance.objects.get(staff=self.staff, date=self.base.date())
        self.assertEqual(row.time_in, self.base.time())
        self.assertEqual(row.time_out, (self.base + timedelta(seconds=1800)).time())

    def test_late_threshold_and_no_threshold_present(self):
        base_seconds = (
            self.base.hour * 3600 + self.base.minute * 60 + self.base.second
        )
        if base_seconds == 0:
            self.base += timedelta(seconds=1)
            base_seconds = 1
        threshold_seconds = base_seconds - 1
        self.policy.student_late_after = time(
            threshold_seconds // 3600,
            (threshold_seconds % 3600) // 60,
            threshold_seconds % 60,
        )
        self.policy.save(update_fields=("student_late_after",))
        self.scan(request_id="late")
        self.assertTrue(StudentAttendance.objects.get().status.late)
        StudentAttendance.objects.all().delete()
        self.policy.student_late_after = None
        self.policy.save(update_fields=("student_late_after",))
        self.scan(seconds=20, request_id="present")
        self.assertFalse(StudentAttendance.objects.get().status.late)

    def test_manual_absent_then_entry_becomes_present_and_preserves_events(self):
        StudentAttendanceService.mark_manual(student=self.student, attendance_date=self.base.date(), classroom=None, status_name="Absent", marked_by=self.admin)
        self.scan(request_id="after-absent")
        row = StudentAttendance.objects.get()
        self.assertFalse(row.status.absent)
        self.assertEqual(set(AttendanceEvent.objects.values_list("source", flat=True)), {AttendanceEvent.Source.MANUAL, AttendanceEvent.Source.RFID})

    def test_duplicate_scan_is_retained_without_second_event_or_time_change(self):
        first = self.scan(seconds=0, request_id="dup-1")
        duplicate = self.scan(seconds=2, request_id="dup-2")
        self.assertEqual((first.result, duplicate.result), (AttendanceScan.Result.SUCCESS, AttendanceScan.Result.DUPLICATE))
        self.assertEqual(AttendanceScan.objects.count(), 2)
        self.assertEqual(AttendanceEvent.objects.filter(source=AttendanceEvent.Source.RFID).count(), 1)
        self.assertEqual(StudentAttendance.objects.get().time_in, self.base.time())

    def test_rfid_disabled_retains_scan_without_daily_attendance(self):
        self.policy.device_attendance_enabled = False
        self.policy.save(update_fields=("device_attendance_enabled",))
        scan = self.scan(request_id="disabled")
        self.assertEqual(scan.result, AttendanceScan.Result.RFID_DISABLED)
        self.assertTrue(AttendanceScan.objects.filter(pk=scan.pk).exists())
        self.assertFalse(StudentAttendance.objects.exists())

    def test_ingestion_requires_valid_device_headers_and_rejects_replay(self):
        payload = {"uid": "04A62792", "scanned_at": self.base.isoformat(), "direction": "ENTRY"}
        view = DeviceScanIngestView.as_view()
        self.assertEqual(view(self.factory.post("/api/attendance/device-scans/", payload, format="json")).status_code, 401)
        timestamp = str(int(timezone.now().timestamp()))
        request = self.factory.post("/api/attendance/device-scans/", payload, format="json")
        signature = AttendanceDeviceService.sign_request(secret=self.secret, method="POST", path=request.path, request_timestamp=timestamp, request_id="api-request", body=request.body)
        headers = {"HTTP_X_DEVICE_ID": "gate-01", "HTTP_X_DEVICE_SECRET": self.secret, "HTTP_X_REQUEST_TIMESTAMP": timestamp, "HTTP_X_REQUEST_ID": "api-request", "HTTP_X_DEVICE_SIGNATURE": signature}
        response = view(self.factory.post("/api/attendance/device-scans/", payload, format="json", **headers))
        self.assertEqual(response.status_code, 200, response.data)
        replay = view(self.factory.post("/api/attendance/device-scans/", payload, format="json", **headers))
        self.assertEqual(replay.status_code, 401)

    def test_management_device_endpoint_is_admin_only_and_secret_once(self):
        payload = {"name": "Side Gate", "device_identifier": "SIDE-1", "mode": "ENTRY"}
        view = AttendanceDeviceViewSet.as_view({"post": "create"})
        anonymous = view(self.factory.post("/api/attendance/devices/", payload, format="json"))
        teacher_request = self.factory.post("/api/attendance/devices/", payload, format="json")
        force_authenticate(teacher_request, user=self.teacher)
        admin_request = self.factory.post("/api/attendance/devices/", payload, format="json")
        force_authenticate(admin_request, user=self.admin)
        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(view(teacher_request).status_code, 403)
        response = view(admin_request)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIn("secret", response.data)
        self.assertNotIn("secret_hash", response.data)
