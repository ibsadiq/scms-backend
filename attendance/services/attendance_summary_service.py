from django.db import transaction

from attendance.models import StudentAttendance, StudentTermAttendanceSummary


class AttendanceSummaryService:
    """Resolves report-card attendance independently from daily capture methods."""

    @classmethod
    def calculate_from_ssync(cls, *, student, term):
        records = StudentAttendance.objects.filter(
            student=student,
            date__gte=term.start_date,
            date__lte=term.end_date,
        ).select_related("status")

        school_days = cls._operational_school_days(term=term)
        days_absent = records.filter(status__absent=True).count()
        times_late = records.filter(status__late=True).count()
        days_present = records.filter(status__absent=False).count()

        summary = StudentTermAttendanceSummary(
            student=student,
            term=term,
            school_days=school_days,
            days_present=days_present,
            days_absent=days_absent,
            times_late=times_late,
            source=StudentTermAttendanceSummary.Source.SSYNC,
            notes="School days use distinct dates with recorded SSync student attendance; this is not an authoritative academic calendar.",
        )
        summary.full_clean(validate_unique=False, validate_constraints=False)
        return summary

    @staticmethod
    def _operational_school_days(*, term):
        return StudentAttendance.objects.filter(
            date__gte=term.start_date,
            date__lte=term.end_date,
        ).values("date").distinct().count()

    @classmethod
    def get_for_report_card(cls, *, student, term):
        persisted = StudentTermAttendanceSummary.objects.filter(student=student, term=term).first()
        if persisted and persisted.source in {
            StudentTermAttendanceSummary.Source.MANUAL,
            StudentTermAttendanceSummary.Source.IMPORTED,
        }:
            return persisted

        has_daily_records = StudentAttendance.objects.filter(
            student=student, date__gte=term.start_date, date__lte=term.end_date
        ).exists()
        if not has_daily_records and not persisted:
            return None
        return cls.calculate_from_ssync(student=student, term=term)

    @classmethod
    @transaction.atomic
    def save_manual_summary(cls, *, student, term, entered_by, school_days,
                            days_present, days_absent, times_late=0, notes=""):
        return cls._save_external_summary(
            student=student, term=term, entered_by=entered_by,
            school_days=school_days, days_present=days_present, days_absent=days_absent,
            times_late=times_late, notes=notes,
            source=StudentTermAttendanceSummary.Source.MANUAL,
        )

    @classmethod
    @transaction.atomic
    def save_imported_summary(cls, *, student, term, entered_by=None, school_days,
                              days_present, days_absent, times_late=0, notes=""):
        return cls._save_external_summary(
            student=student, term=term, entered_by=entered_by,
            school_days=school_days, days_present=days_present, days_absent=days_absent,
            times_late=times_late, notes=notes,
            source=StudentTermAttendanceSummary.Source.IMPORTED,
        )

    @staticmethod
    def _save_external_summary(**values):
        student = values.pop("student")
        term = values.pop("term")
        candidate = StudentTermAttendanceSummary(student=student, term=term, **values)
        candidate.full_clean(validate_unique=False, validate_constraints=False)
        summary, _ = StudentTermAttendanceSummary.objects.update_or_create(
            student=student, term=term, defaults=values
        )
        return summary
