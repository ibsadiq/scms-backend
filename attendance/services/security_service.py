import hashlib
from datetime import timedelta

from django.conf import settings
from django.db.models import F
from django.utils import timezone

from attendance.models import AttendanceDevice, DeviceSecurityEvent


class DeviceSecurityEventService:
    DEDUPLICATION_WINDOW = timedelta(minutes=5)

    @classmethod
    def record(cls, *, event_type, severity, device=None, request_id="", details=None, fingerprint=""):
        safe_details = {str(key)[:40]: str(value)[:160] for key, value in (details or {}).items()}
        if not fingerprint:
            material = f"{device.pk if device else 'unknown'}:{event_type}"
            fingerprint = hashlib.sha256(material.encode()).hexdigest()
        now = timezone.now()
        existing = DeviceSecurityEvent.objects.filter(
            device=device, event_type=event_type, fingerprint=fingerprint,
            last_occurred_at__gte=now - cls.DEDUPLICATION_WINDOW,
        ).first()
        if existing:
            DeviceSecurityEvent.objects.filter(pk=existing.pk).update(
                occurrence_count=F("occurrence_count") + 1, last_occurred_at=now,
            )
            existing.refresh_from_db()
            return existing
        return DeviceSecurityEvent.objects.create(
            device=device, event_type=event_type, severity=severity, request_id=str(request_id)[:64],
            details=safe_details, fingerprint=fingerprint, last_occurred_at=now,
        )


class DeviceHealthService:
    @classmethod
    def stale_after(cls):
        return timedelta(seconds=getattr(settings, "RFID_DEVICE_STALE_SECONDS", 600))

    @classmethod
    def offline_after(cls):
        return timedelta(seconds=getattr(settings, "RFID_DEVICE_OFFLINE_SECONDS", 1800))

    @classmethod
    def status(cls, device, now=None):
        if not device.is_active:
            return "DISABLED"
        if not device.last_seen_at:
            return "OFFLINE"
        age = (now or timezone.now()) - device.last_seen_at
        if age >= cls.offline_after():
            return "OFFLINE"
        if age >= cls.stale_after():
            return "STALE"
        return "RECENT"
