import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from school.testcases import TenantTestCase
from rest_framework.test import APIRequestFactory

from academic.models import Student
from attendance.models import AttendanceDevice, AttendanceEvent, AttendancePolicy, AttendanceScan, DeviceSecurityEvent, StudentAttendance
from attendance.services import AttendanceDeviceService, AttendanceScanRetentionService, DeviceHealthService, StudentAttendanceService
from attendance.views_device import DeviceScanIngestView


User = get_user_model()


class RFIDHardeningTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        return super().setup_tenant(tenant)

    def setUp(self):
        cache.clear()
        self.device, self.secret = AttendanceDeviceService.register(
            name="Hardened Gate", device_identifier="HARD-1", mode=AttendanceDevice.Mode.ENTRY
        )
        self.policy = AttendancePolicy.objects.create(device_attendance_enabled=False)
        self.factory = APIRequestFactory()
        self.view = DeviceScanIngestView.as_view()
        self.path = "/api/attendance/device-scans/"
        self.payload = {"uid": "04A62792", "scanned_at": timezone.now().isoformat(), "direction": "ENTRY"}

    def signed_request(self, *, payload=None, request_id="hard-1", timestamp=None, secret=None, signed_payload=None, signed_request_id=None, signed_timestamp=None, signature=None):
        payload = payload or self.payload
        timestamp = timestamp or str(int(timezone.now().timestamp()))
        request = self.factory.post(self.path, payload, format="json")
        if signature is None:
            body_to_sign = request.body if signed_payload is None else json.dumps(signed_payload, separators=(",", ":")).encode()
            signature = AttendanceDeviceService.sign_request(
                secret=secret or self.secret, method="POST", path=self.path,
                request_timestamp=signed_timestamp or timestamp,
                request_id=signed_request_id or request_id, body=body_to_sign,
            )
        return self.factory.post(
            self.path, payload, format="json", HTTP_X_DEVICE_ID=self.device.device_identifier,
            HTTP_X_DEVICE_SECRET=secret or self.secret, HTTP_X_REQUEST_TIMESTAMP=timestamp,
            HTTP_X_REQUEST_ID=request_id, HTTP_X_DEVICE_SIGNATURE=signature,
        )

    def test_valid_hmac_is_accepted_and_updates_last_seen(self):
        response = self.view(self.signed_request())
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["result"], AttendanceScan.Result.RFID_DISABLED)
        self.device.refresh_from_db()
        self.assertIsNotNone(self.device.last_seen_at)

    def test_modified_body_timestamp_wrong_signature_and_request_id_are_rejected(self):
        cases = [
            self.signed_request(payload={**self.payload, "uid": "DEADBEEF"}, signed_payload=self.payload, request_id="body"),
            self.signed_request(request_id="timestamp", timestamp=str(int(timezone.now().timestamp()) + 1), signed_timestamp=str(int(timezone.now().timestamp()))),
            self.signed_request(request_id="wrong", signature="0" * 64),
            self.signed_request(request_id="new-id", signed_request_id="old-id"),
        ]
        for request in cases:
            response = self.view(request)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.data["result"], "INVALID_SIGNATURE")

    def test_replay_and_expired_request_timestamp_are_rejected(self):
        first = self.view(self.signed_request(request_id="replay"))
        replay = self.view(self.signed_request(request_id="replay"))
        old = str(int((timezone.now() - timedelta(minutes=6)).timestamp()))
        expired = self.view(self.signed_request(request_id="old", timestamp=old))
        self.assertEqual(first.status_code, 200)
        self.assertEqual((replay.status_code, replay.data["result"]), (401, "REPLAY_REJECTED"))
        self.assertEqual((expired.status_code, expired.data["result"]), (401, "INVALID_TIMESTAMP"))

    def test_secret_rotation_invalidates_old_hmac_and_accepts_new(self):
        old_request = self.signed_request(request_id="old-secret")
        new_secret = AttendanceDeviceService.rotate_secret(self.device)
        self.assertEqual(self.view(old_request).status_code, 401)
        response = self.view(self.signed_request(request_id="new-secret", secret=new_secret))
        self.assertEqual(response.status_code, 200, response.data)

    @override_settings(RFID_DEVICE_BURST_LIMIT=2, RFID_DEVICE_BURST_WINDOW=60, RFID_DEVICE_SUSTAINED_LIMIT=10)
    def test_rate_limit_allows_normal_traffic_throttles_excess_and_isolates_devices(self):
        self.assertEqual(self.view(self.signed_request(request_id="rate-1")).status_code, 200)
        self.assertEqual(self.view(self.signed_request(request_id="rate-2")).status_code, 200)
        limited = self.view(self.signed_request(request_id="rate-3"))
        self.assertEqual((limited.status_code, limited.data["result"]), (429, "RATE_LIMITED"))
        other, other_secret = AttendanceDeviceService.register(name="Other", device_identifier="HARD-2", mode=AttendanceDevice.Mode.ENTRY)
        self.device, self.secret = other, other_secret
        self.assertEqual(self.view(self.signed_request(request_id="other-1")).status_code, 200)

    @override_settings(RFID_DEVICE_STALE_SECONDS=600, RFID_DEVICE_OFFLINE_SECONDS=1800)
    def test_health_derives_recent_stale_offline_and_disabled(self):
        now = timezone.now()
        self.device.last_seen_at = now - timedelta(minutes=1)
        self.assertEqual(DeviceHealthService.status(self.device, now), "RECENT")
        self.device.last_seen_at = now - timedelta(minutes=15)
        self.assertEqual(DeviceHealthService.status(self.device, now), "STALE")
        self.device.last_seen_at = now - timedelta(minutes=31)
        self.assertEqual(DeviceHealthService.status(self.device, now), "OFFLINE")
        self.device.is_active = False
        self.assertEqual(DeviceHealthService.status(self.device, now), "DISABLED")

    def test_security_events_log_and_deduplicate_invalid_signature_replay_and_rate(self):
        self.view(self.signed_request(request_id="bad-1", signature="0" * 64))
        self.view(self.signed_request(request_id="bad-2", signature="0" * 64))
        event = DeviceSecurityEvent.objects.get(event_type=DeviceSecurityEvent.EventType.INVALID_SIGNATURE)
        self.assertEqual(event.occurrence_count, 2)
        self.view(self.signed_request(request_id="replay-event"))
        self.view(self.signed_request(request_id="replay-event"))
        self.assertTrue(DeviceSecurityEvent.objects.filter(event_type=DeviceSecurityEvent.EventType.REPLAY_ATTEMPT).exists())

    def test_opt_in_retention_removes_only_old_raw_scans(self):
        student = Student.objects.create(first_name="Retention", last_name="Student", parent_contact="08040000001")
        actor = User.objects.create_user(email="retention@example.com", password="test", is_admin=True)
        attendance, _ = StudentAttendanceService.mark_manual(
            student=student, attendance_date=timezone.localdate(), classroom=None,
            status_name="Present", marked_by=actor,
        )
        old = AttendanceScan.objects.create(device=self.device, raw_uid="DEADBEEF", request_id="retention-old", scanned_at=timezone.now(), result=AttendanceScan.Result.UNKNOWN_CARD)
        recent = AttendanceScan.objects.create(device=self.device, raw_uid="AABBCCDD", request_id="retention-new", scanned_at=timezone.now(), result=AttendanceScan.Result.UNKNOWN_CARD)
        AttendanceScan.objects.filter(pk=old.pk).update(received_at=timezone.now() - timedelta(days=31))
        self.policy.raw_scan_retention_days = 30
        self.policy.save(update_fields=("raw_scan_retention_days",))
        self.assertEqual(AttendanceScanRetentionService.cleanup(), 1)
        self.assertFalse(AttendanceScan.objects.filter(pk=old.pk).exists())
        self.assertTrue(AttendanceScan.objects.filter(pk=recent.pk).exists())
        self.assertTrue(StudentAttendance.objects.filter(pk=attendance.pk).exists())
        self.assertTrue(AttendanceEvent.objects.filter(student=student).exists())
