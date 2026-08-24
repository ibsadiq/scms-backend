from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from examination.models import AssessmentEntry

from ..models import (
    AttemptGrade,
    AttemptGradingStatus,
)
from .cbt_actor_service import CBTActorService


class ResultPostingService:

    @staticmethod
    @transaction.atomic
    def post(
        *,
        attempt_grade,
        posted_by,
    ):
        teacher = CBTActorService.resolve_teacher(posted_by)

        attempt_grade = (
            AttemptGrade.objects
            .select_for_update()
            .select_related(
                "attempt",
                "attempt__student",
                "attempt__enrollment",
                "attempt__cbt_exam",
                "attempt__cbt_exam__session",
                "attempt__cbt_exam__subject",
                "attempt__cbt_exam__component",
            )
            .get(pk=attempt_grade.pk)
        )

        if (
            attempt_grade.status
            == AttemptGradingStatus.POSTED
        ):
            return attempt_grade

        if (
            attempt_grade.status
            != AttemptGradingStatus.GRADED
        ):
            raise ValidationError(
                "Only fully graded CBT attempts "
                "can be posted to results."
            )

        if attempt_grade.normalized_score is None:
            raise ValidationError(
                "The normalized CBT score is missing."
            )

        attempt = attempt_grade.attempt
        exam = attempt.cbt_exam
        session = exam.session

        source_reference = (
            f"cbt-attempt:{attempt.pk}"
        )

        AssessmentEntry.objects.update_or_create(
            student=attempt.enrollment,
            subject=exam.subject,
            component=exam.component,
            defaults={
                "session": session,
                "term": session.term,
                "academic_year": session.academic_year,
                "score": attempt_grade.normalized_score,
                "source": AssessmentEntry.EntrySource.CBT,
                "source_reference": source_reference,
                "entered_by": teacher,
                "status": AssessmentEntry.EntryStatus.COMPLETE,
            },
        )

        attempt_grade.status = (
            AttemptGradingStatus.POSTED
        )

        attempt_grade.posted_at = timezone.now()

        attempt_grade.save(
            update_fields=[
                "status",
                "posted_at",
                "updated_at",
            ]
        )

        return attempt_grade