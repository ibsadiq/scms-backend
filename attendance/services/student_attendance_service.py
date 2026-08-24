from django.db import transaction
from academic.models import Student
from administration.models import Term
from attendance.models import AttendanceEvent, StudentAttendance
from .attendance_event_service import AttendanceEventService
from .attendance_status_service import AttendanceStatusService
from .attendance_policy_service import AttendancePolicyService
from .notification_service import AttendanceNotificationService


class StudentAttendanceService:
    EVENT_BY_STATUS = {
        "Present": AttendanceEvent.EventType.MARKED_PRESENT,
        "Absent": AttendanceEvent.EventType.MARKED_ABSENT,
        "Late": AttendanceEvent.EventType.MARKED_LATE,
    }

    @staticmethod
    def resolve_term(attendance_date):
        return Term.objects.filter(start_date__lte=attendance_date, end_date__gte=attendance_date).order_by("-start_date").first()

    @classmethod
    @transaction.atomic
    def mark_manual(cls, *, student, attendance_date, classroom, status_name,
                    marked_by, notes="", time_in=None, time_out=None, term=None):
        student = Student.objects.select_for_update().get(pk=student.pk)
        status = AttendanceStatusService.resolve(status_name)
        existing = StudentAttendance.objects.filter(student=student, date=attendance_date).first()
        was_absent = bool(existing and existing.status.absent)
        previous = cls._state(existing)
        attendance, created = StudentAttendance.objects.update_or_create(
            student=student, date=attendance_date,
            defaults={"ClassRoom": classroom, "status": status, "notes": notes,
                      "term": term or cls.resolve_term(attendance_date), "marked_by": marked_by,
                      "time_in": time_in, "time_out": time_out},
        )
        AttendanceEventService.record(
            student=student, source=AttendanceEvent.Source.MANUAL,
            event_type=cls.EVENT_BY_STATUS.get(status.name, AttendanceEvent.EventType.STATUS_CHANGED) if created else AttendanceEvent.EventType.MANUAL_CORRECTION,
            performed_by=marked_by, previous_state=previous, new_state=cls._state(attendance),
        )
        AttendanceNotificationService.schedule_transition(
            student=student, attendance_date=attendance_date,
            was_absent=was_absent, is_absent=status.absent,
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
    def mark_rfid(cls, *, student, occurred_at, direction, metadata=None):
        student = Student.objects.select_for_update().get(pk=student.pk)
        local = occurred_at.astimezone()
        attendance_date, scan_time = local.date(), local.time().replace(tzinfo=None)
        current = StudentAttendance.objects.select_for_update().filter(student=student, date=attendance_date).first()
        was_absent = bool(current and current.status.absent)
        previous = cls._state(current)
        policy = AttendancePolicyService.get_current()
        status_name = "Late" if direction == AttendanceEvent.EventType.ENTRY and policy.student_late_after and scan_time > policy.student_late_after else "Present"
        status = AttendanceStatusService.resolve(status_name)
        if direction == AttendanceEvent.EventType.ENTRY:
            time_in = current.time_in if current and current.time_in else scan_time
            time_out = current.time_out if current else None
        else:
            time_in = current.time_in if current else None
            time_out = scan_time
            if current and not current.status.absent:
                status = current.status
        attendance, _ = StudentAttendance.objects.update_or_create(
            student=student, date=attendance_date,
            defaults={
                "ClassRoom": student.classroom, "term": cls.resolve_term(attendance_date), "status": status,
                "time_in": time_in, "time_out": time_out, "notes": current.notes if current else "",
                "marked_by": current.marked_by if current else None,
            },
        )
        AttendanceEventService.record(
            student=student, source=AttendanceEvent.Source.RFID, event_type=direction,
            occurred_at=occurred_at, previous_state=previous, new_state=cls._state(attendance), metadata=metadata,
        )
        AttendanceNotificationService.schedule_transition(
            student=student, attendance_date=attendance_date,
            was_absent=was_absent, is_absent=status.absent,
        )
        return attendance
