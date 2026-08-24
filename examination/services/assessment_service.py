from django.core.exceptions import ValidationError
from django.db import transaction
from academic.models import AllocatedSubject
from ..models import AssessmentEntry


class AssessmentService:

    @staticmethod
    @transaction.atomic
    def record_score(*, component, student, subject, score, teacher, term, academic_year, session=None, status="COMPLETE", source="MANUAL", remarks=""):
        """
        Create or update a single score entry.
        Authorization + score-range checks live in AssessmentEntry.clean(),
        this just ensures clean() actually runs before save.
        """
        from academic.models import StudentClassEnrollment, AcademicYear
        enrollment = StudentClassEnrollment.objects.select_for_update().filter(
            student_id=student,
            academic_year=academic_year,
            is_active=True
        ).first()

        if not enrollment:
            raise ValidationError(f"Student ID {student} is not actively enrolled in the given academic year.")

        from ..models import TermResult, Term
        term_result = TermResult.objects.select_for_update().filter(
            student_id=student,
            term=term,
            academic_year=academic_year,
        ).first()
        if term_result and term_result.is_locked:
            raise ValidationError(f"Term result for this student is locked. Unlock result to modify scores.")

        entry, created = AssessmentEntry.objects.update_or_create(
            component_id=component,
            student=enrollment,
            subject_id=subject,
            term=term,
            academic_year=academic_year,
            defaults={
                "session_id": session,
                "score": score,
                "status": status,
                "source": source,
                "entered_by": teacher,
                "remarks": remarks,
            },
        )
        entry.full_clean()
        entry.save()
        return entry

    @staticmethod
    @transaction.atomic
    def finalize_cbt_score(*, component, student, subject, score, teacher, term, academic_year, source_reference, session=None, remarks=""):
        """
        Idempotent entry point for finalizing a CBT score.
        """
        from academic.models import StudentClassEnrollment
        from ..models import AssessmentEntry, TermResult
        from django.db import IntegrityError
        
        # Check if this exact CBT attempt was already finalized (idempotent success)
        existing = AssessmentEntry.objects.filter(source_reference=source_reference).first()
        if existing:
            return existing
            
        enrollment = StudentClassEnrollment.objects.select_for_update().filter(
            student_id=student,
            academic_year=academic_year,
            is_active=True
        ).first()

        if not enrollment:
            raise ValidationError(f"Student ID {student} is not actively enrolled in the given academic year.")
            
        # Verify target result is not locked
        term_result = TermResult.objects.select_for_update().filter(
            student_id=student,
            term=term,
            academic_year=academic_year
        ).first()
        
        if term_result and term_result.is_locked:
            raise ValidationError(f"Term result for this student is locked. Cannot ingest CBT score.")
            
        try:
            # We attempt to create or update. Because of unique_student_component_score,
            # this might raise an IntegrityError if another request creates the row first.
            with transaction.atomic():
                entry, created = AssessmentEntry.objects.update_or_create(
                    component_id=component,
                    student=enrollment,
                    subject_id=subject,
                    term=term,
                    academic_year=academic_year,
                    defaults={
                        "session_id": session,
                        "score": score,
                        "status": AssessmentEntry.EntryStatus.COMPLETE,
                        "source": AssessmentEntry.EntrySource.CBT,
                        "source_reference": source_reference,
                        "entered_by": teacher,
                        "remarks": remarks,
                    },
                )
                entry.full_clean()
                entry.save()
                return entry
        except IntegrityError:
            # A race condition occurred. We either hit the unique_student_component_score
            # or the unique source_reference constraint. 
            # Re-fetch to see what happened.
            existing_ref = AssessmentEntry.objects.filter(source_reference=source_reference).first()
            if existing_ref:
                return existing_ref
                
            # If it wasn't the source_reference, then the student/component slot was taken
            # by a DIFFERENT source_reference (another CBT attempt or manual entry).
            # Policy: reject the new attempt if the slot is already taken by a different attempt.
            raise ValidationError("An assessment entry already exists for this student and component from a different attempt/source.")

    @staticmethod
    @transaction.atomic
    def bulk_record_scores(*, entries, teacher, term, academic_year, session=None, status="COMPLETE", source="MANUAL"):
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
                        term=term,
                        academic_year=academic_year,
                        session=session,
                        status=row.get("status", status),
                        source=row.get("source", source),
                        remarks=row.get("remarks", ""),
                    )
                )
            except ValidationError as e:
                errors[i] = e.message_dict if hasattr(e, "message_dict") else str(e)

        if errors:
            raise ValidationError({"bulk_errors": errors})
        return results
