from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.utils import timezone


class DeviceRateLimitExceeded(Exception):
    pass


class DeviceRateLimitService:
    @classmethod
    def _limits(cls):
        return (
            ("burst", getattr(settings, "RFID_DEVICE_BURST_LIMIT", 30), getattr(settings, "RFID_DEVICE_BURST_WINDOW", 10)),
            ("sustained", getattr(settings, "RFID_DEVICE_SUSTAINED_LIMIT", 600), getattr(settings, "RFID_DEVICE_SUSTAINED_WINDOW", 60)),
        )

    @classmethod
    def check(cls, device):
        now = int(timezone.now().timestamp())
        for label, limit, window in cls._limits():
            bucket = now // window
            key = f"rfid-rate:{connection.schema_name}:{device.pk}:{label}:{bucket}"
            if cache.add(key, 1, timeout=window + 1):
                count = 1
            else:
                try:
                    count = cache.incr(key)
                except ValueError:
                    cache.set(key, 1, timeout=window + 1)
                    count = 1
            if count > limit:
                raise DeviceRateLimitExceeded(label)
