from datetime import timedelta

from django.utils import timezone

from attendance.models import AttendanceScan
from .attendance_policy_service import AttendancePolicyService


class AttendanceScanRetentionService:
    @classmethod
    def cleanup(cls, *, now=None):
        policy = AttendancePolicyService.get_current()
        if not policy.raw_scan_retention_days:
            return 0
        cutoff = (now or timezone.now()) - timedelta(days=policy.raw_scan_retention_days)
        deleted, _ = AttendanceScan.objects.filter(received_at__lt=cutoff).delete()
        return deleted
