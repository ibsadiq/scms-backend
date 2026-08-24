import secrets
import hashlib
import hmac
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.utils import timezone

from attendance.models import AttendanceDevice, AttendanceScan, DeviceSecurityEvent
from .security_service import DeviceSecurityEventService


class DeviceAuthenticationError(Exception):
    def __init__(self, result, message, device=None):
        super().__init__(message)
        self.result = result
        self.device = device


class AttendanceDeviceService:
    REQUEST_WINDOW = timedelta(minutes=5)

    @classmethod
    def _secret(cls):
        return secrets.token_urlsafe(32)

    @classmethod
    def register(cls, *, name, device_identifier, mode, location=""):
        secret = cls._secret()
        device = AttendanceDevice.objects.create(
            name=name, device_identifier=str(device_identifier).strip().upper(), mode=mode,
            location=location, secret_hash=make_password(secret),
        )
        return device, secret

    @classmethod
    def rotate_secret(cls, device):
        secret = cls._secret()
        device.secret_hash = make_password(secret)
        device.save(update_fields=("secret_hash", "updated_at"))
        return secret

    @staticmethod
    def canonical_request(*, method, path, request_timestamp, request_id, body):
        body_hash = hashlib.sha256(body).hexdigest()
        return "\n".join((method.upper(), path, str(request_timestamp), str(request_id), body_hash)).encode("utf-8")

    @classmethod
    def sign_request(cls, *, secret, method, path, request_timestamp, request_id, body):
        canonical = cls.canonical_request(
            method=method, path=path, request_timestamp=request_timestamp, request_id=request_id, body=body
        )
        return hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()

    @classmethod
    def authenticate(cls, *, identifier, secret, request_timestamp, request_id, signature, method, path, body):
        try:
            device = AttendanceDevice.objects.get(device_identifier=str(identifier or "").strip().upper())
        except AttendanceDevice.DoesNotExist as exc:
            raise DeviceAuthenticationError("INVALID_CREDENTIALS", "Invalid device credentials.") from exc
        if not secret or not check_password(secret, device.secret_hash):
            DeviceSecurityEventService.record(
                device=device, event_type=DeviceSecurityEvent.EventType.INVALID_SECRET,
                severity=DeviceSecurityEvent.Severity.WARNING, request_id=request_id,
            )
            raise DeviceAuthenticationError("INVALID_CREDENTIALS", "Invalid device credentials.", device)
        if not request_id or len(request_id) > 64:
            raise DeviceAuthenticationError("INVALID_REQUEST_ID", "A valid request ID is required.", device)
        try:
            submitted = timezone.datetime.fromtimestamp(int(request_timestamp), tz=timezone.get_current_timezone())
        except (TypeError, ValueError, OverflowError) as exc:
            raise DeviceAuthenticationError("INVALID_TIMESTAMP", "Invalid request timestamp.", device) from exc
        if abs(timezone.now() - submitted) > cls.REQUEST_WINDOW:
            raise DeviceAuthenticationError("INVALID_TIMESTAMP", "Request timestamp is outside the accepted window.", device)
        if AttendanceScan.objects.filter(device=device, request_id=request_id).exists():
            DeviceSecurityEventService.record(
                device=device, event_type=DeviceSecurityEvent.EventType.REPLAY_ATTEMPT,
                severity=DeviceSecurityEvent.Severity.WARNING, request_id=request_id,
            )
            raise DeviceAuthenticationError("REPLAY_REJECTED", "Request has already been processed.", device)
        expected = cls.sign_request(
            secret=secret, method=method, path=path, request_timestamp=request_timestamp,
            request_id=request_id, body=body,
        )
        if not signature or not hmac.compare_digest(expected, str(signature).lower()):
            DeviceSecurityEventService.record(
                device=device, event_type=DeviceSecurityEvent.EventType.INVALID_SIGNATURE,
                severity=DeviceSecurityEvent.Severity.CRITICAL, request_id=request_id,
            )
            raise DeviceAuthenticationError("INVALID_SIGNATURE", "Invalid request signature.", device)
        device.last_seen_at = timezone.now()
        device.save(update_fields=("last_seen_at", "updated_at"))
        return device
