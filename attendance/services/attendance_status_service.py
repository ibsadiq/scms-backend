from django.core.exceptions import ValidationError
from django.db import transaction
from attendance.models import AttendanceStatus


class AttendanceStatusService:
    CANONICAL = {
        "Present": {"code": "P"},
        "Absent": {"code": "A", "absent": True},
        "Late": {"code": "L", "late": True},
        "Excused": {"code": "E", "excused": True},
    }

    @classmethod
    @transaction.atomic
    def resolve(cls, name):
        normalized = str(name or "").strip().title()
        if normalized not in cls.CANONICAL:
            raise ValidationError({"status": f"Unsupported attendance status: {name}"})
        existing = AttendanceStatus.objects.filter(name__iexact=normalized).first()
        if existing:
            return existing
        defaults = cls.CANONICAL[normalized]
        if AttendanceStatus.objects.filter(code__iexact=defaults["code"]).exists():
            raise ValidationError({"status": f"Canonical code {defaults['code']} is already in use."})
        return AttendanceStatus.objects.create(name=normalized, **defaults)
