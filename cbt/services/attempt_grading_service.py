from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from ..models import (
    ExamAttempt,
    ExamAttemptStatus,
    AttemptGrade,
    AttemptGradingStatus,
    QuestionGradingStatus,
)

from .objective_grading_service import (
    ObjectiveGradingService,
)


class AttemptGradingService:

    TWO_PLACES = Decimal("0.01")

    @staticmethod
    @transaction.atomic
    def grade_attempt(
        *,
        attempt,
    ):
        attempt = (
            ExamAttempt.objects
            .select_for_update()
            .select_related(
                "cbt_exam",
                "cbt_exam__component",
            )
            .get(pk=attempt.pk)
        )

        if (
            attempt.status
            != ExamAttemptStatus.SUBMITTED
        ):
            raise ValidationError(
                "Only submitted CBT attempts "
                "can be graded."
            )

        attempt_questions = list(
            attempt.attempt_questions
            .select_related(
                "exam_question",
                "exam_question__question_version",
            )
            .order_by("display_order")
        )

        if not attempt_questions:
            raise ValidationError(
                "This attempt does not contain any questions."
            )

        for attempt_question in attempt_questions:
            (
                ObjectiveGradingService
                .grade_question(
                    attempt_question=attempt_question
                )
            )

        return (
            AttemptGradingService
            .refresh_summary(
                attempt=attempt
            )
        )

    @staticmethod
    @transaction.atomic
    def refresh_summary(
        *,
        attempt,
    ):
        attempt = (
            ExamAttempt.objects
            .select_for_update()
            .select_related(
                "cbt_exam",
                "cbt_exam__component",
            )
            .get(pk=attempt.pk)
        )

        question_grades = (
            attempt.attempt_questions
            .filter(
                grade__isnull=False
            )
            .select_related("grade")
        )

        total_questions = (
            attempt.attempt_questions.count()
        )

        graded_count = (
            question_grades.count()
        )

        if graded_count != total_questions:
            raise ValidationError(
                "Not every attempt question has "
                "a grading record."
            )

        pending_manual = (
            question_grades.filter(
                grade__status=
                    QuestionGradingStatus.PENDING_MANUAL
            )
            .exists()
        )

        totals = (
            question_grades.aggregate(
                raw_score=Sum(
                    "grade__awarded_marks"
                ),
                total_marks=Sum(
                    "grade__max_marks"
                ),
            )
        )

        raw_score = (
            totals["raw_score"]
            or Decimal("0")
        )

        total_marks = (
            totals["total_marks"]
            or Decimal("0")
        )

        if total_marks <= 0:
            raise ValidationError(
                "Attempt total marks must be greater than zero."
            )

        percentage = (
            (
                raw_score
                / total_marks
            )
            * Decimal("100")
        ).quantize(
            AttemptGradingService.TWO_PLACES,
            rounding=ROUND_HALF_UP,
        )

        normalized_score = None

        if not pending_manual:
            component_max = Decimal(
                str(
                    attempt
                    .cbt_exam
                    .component
                    .max_score
                )
            )

            normalized_score = (
                (
                    raw_score
                    / total_marks
                )
                * component_max
            ).quantize(
                AttemptGradingService.TWO_PLACES,
                rounding=ROUND_HALF_UP,
            )

        grade, _ = (
            AttemptGrade.objects
            .update_or_create(
                attempt=attempt,
                defaults={
                    "raw_score":
                        raw_score,
                    "total_marks":
                        total_marks,
                    "percentage":
                        percentage,
                    "normalized_score":
                        normalized_score,
                    "status": (
                        AttemptGradingStatus.NEEDS_MANUAL
                        if pending_manual
                        else AttemptGradingStatus.GRADED
                    ),
                    "graded_at": (
                        None
                        if pending_manual
                        else timezone.now()
                    ),
                },
            )
        )

        return grade