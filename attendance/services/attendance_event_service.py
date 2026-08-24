from django.utils import timezone
from attendance.models import AttendanceEvent


class AttendanceEventService:
    @staticmethod
    def record(*, student=None, staff=None, source, event_type, performed_by=None,
               occurred_at=None, previous_state=None, new_state=None, metadata=None):
        if (student is None) == (staff is None):
            raise ValueError("Exactly one attendance subject is required.")
        return AttendanceEvent.objects.create(
            student=student, staff=staff, source=source, event_type=event_type,
            occurred_at=occurred_at or timezone.now(), performed_by=performed_by,
            previous_state=previous_state or {}, new_state=new_state or {}, metadata=metadata or {},
        )
