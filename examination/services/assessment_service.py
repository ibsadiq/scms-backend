from django.core.exceptions import ValidationError
from django.db import transaction
from academic.models import AllocatedSubject
from ..models import AssessmentEntry


class AssessmentService:

    @staticmethod
    def record_score(*, component, student, subject, score, teacher, remarks=""):
        """
        Create or update a single score entry.
        Authorization + score-range checks live in AssessmentEntry.clean(),
        this just ensures clean() actually runs before save.
        """
        from academic.models import StudentClassEnrollment, AcademicYear
        current_year = AcademicYear.objects.filter(active_year=True).first()
        enrollment = StudentClassEnrollment.objects.filter(
            student_id=student,
            academic_year=current_year,
            is_active=True
        ).first()

        if not enrollment:
            raise ValidationError(f"Student ID {student} is not actively enrolled.")

        from ..models import TermResult, Term
        current_term = Term.objects.filter(academic_year=current_year, is_current=True).first()
        if current_term:
            locked = TermResult.objects.filter(
                student_id=student,
                term=current_term,
                is_locked=True
            ).exists()
            if locked:
                raise ValidationError(f"Term result for this student is locked. Unlock result to modify scores.")

        entry, created = AssessmentEntry.objects.update_or_create(
            component_id=component,
            student=enrollment,
            subject_id=subject,
            defaults={
                "score": score,
                "entered_by": teacher,
                "remarks": remarks,
            },
        )
        entry.full_clean()
        entry.save()
        return entry

    @staticmethod
    @transaction.atomic
    def bulk_record_scores(*, entries, teacher):
        """
        entries: list of dicts with component, student, subject, score, remarks
        Runs each through record_score individually so one bad row doesn't
        silently corrupt the rest — collects errors keyed by row index.
        """
        results, errors = [], {}
        for i, row in enumerate(entries):
            try:
                results.append(
                    AssessmentService.record_score(
                        component=row["component"],
                        student=row["student"],
                        subject=row["subject"],
                        score=row["score"],
                        teacher=teacher,
                        remarks=row.get("remarks", ""),
                    )
                )
            except ValidationError as e:
                errors[i] = e.message_dict if hasattr(e, "message_dict") else str(e)

        if errors:
            raise ValidationError({"bulk_errors": errors})
        return results