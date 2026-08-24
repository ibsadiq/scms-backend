from celery import shared_task
from django.utils import timezone
from django_tenants.utils import schema_context

from tenants.models import Client


@shared_task(name="attendance.monitor_device_health")
def monitor_device_health():
    from attendance.models import AttendanceDevice, DeviceSecurityEvent
    from attendance.services import DeviceHealthService, DeviceSecurityEventService

    alerts = 0
    for schema_name in Client.objects.exclude(schema_name="public").values_list("schema_name", flat=True):
        with schema_context(schema_name):
            for device in AttendanceDevice.objects.filter(is_active=True):
                health = DeviceHealthService.status(device)
                alert_state = health if health in {"STALE", "OFFLINE"} else ""
                if alert_state and device.health_alert_state != alert_state:
                    DeviceSecurityEventService.record(
                        device=device,
                        event_type=(DeviceSecurityEvent.EventType.DEVICE_OFFLINE if health == "OFFLINE" else DeviceSecurityEvent.EventType.DEVICE_STALE),
                        severity=(DeviceSecurityEvent.Severity.CRITICAL if health == "OFFLINE" else DeviceSecurityEvent.Severity.WARNING),
                        details={"health": health},
                    )
                    alerts += 1
                if device.health_alert_state != alert_state:
                    device.health_alert_state = alert_state
                    device.save(update_fields=("health_alert_state", "updated_at"))
    return alerts


@shared_task(name="attendance.cleanup_raw_scans")
def cleanup_raw_scans():
    from attendance.services import AttendanceScanRetentionService

    deleted = 0
    for schema_name in Client.objects.exclude(schema_name="public").values_list("schema_name", flat=True):
        with schema_context(schema_name):
            deleted += AttendanceScanRetentionService.cleanup()
    return deleted
