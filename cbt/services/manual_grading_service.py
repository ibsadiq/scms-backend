from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import (
    ExamAttemptStatus,
    QuestionType,
    QuestionGradingStatus,
    GradingMethod,
    AttemptQuestionGrade,
)

from .attempt_grading_service import (
    AttemptGradingService,
)
from .cbt_actor_service import CBTActorService


class ManualGradingService:

    @staticmethod
    @transaction.atomic
    def grade_essay(
        *,
        attempt_question,
        marks,
        graded_by,
        feedback="",
    ):
        teacher = CBTActorService.resolve_teacher(graded_by)

        attempt_question = (
            attempt_question.__class__.objects
            .select_for_update()
            .select_related(
                "attempt",
                "exam_question",
                "exam_question__question_version",
            )
            .get(pk=attempt_question.pk)
        )

        attempt = attempt_question.attempt

        if (
            attempt.status
            != ExamAttemptStatus.SUBMITTED
        ):
            raise ValidationError(
                "Only submitted attempts "
                "can be manually graded."
            )

        version = (
            attempt_question
            .exam_question
            .question_version
        )

        if (
            version.question_type
            != QuestionType.ESSAY
        ):
            raise ValidationError(
                "Only essay questions require "
                "manual grading."
            )

        try:
            marks = Decimal(str(marks))
        except (
            InvalidOperation,
            TypeError,
            ValueError,
        ):
            raise ValidationError(
                "A valid mark is required."
            )

        max_marks = (
            attempt_question
            .exam_question
            .marks
        )

        if marks < 0:
            raise ValidationError(
                "Marks cannot be negative."
            )

        if marks > max_marks:
            raise ValidationError(
                "Awarded marks cannot exceed "
                "the question maximum marks."
            )

        grade, _ = (
            AttemptQuestionGrade.objects
            .update_or_create(
                attempt_question=attempt_question,
                defaults={
                    "awarded_marks":
                        marks,
                    "max_marks":
                        max_marks,
                    "is_correct":
                        None,
                    "status":
                        QuestionGradingStatus.MANUALLY_GRADED,
                    "grading_method":
                        GradingMethod.MANUAL,
                    "feedback":
                        feedback,
                    "graded_by":
                        teacher,
                    "graded_at":
                        timezone.now(),
                },
            )
        )

        AttemptGradingService.refresh_summary(
            attempt=attempt
        )

        return grade