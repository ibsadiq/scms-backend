from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.utils import timezone

from ..models import (
    QuestionType,
    QuestionGradingStatus,
    GradingMethod,
    AttemptQuestionGrade,
)


class ObjectiveGradingService:

    TWO_PLACES = Decimal("0.01")

    AUTO_TYPES = {
        QuestionType.SINGLE_CHOICE,
        QuestionType.MULTIPLE_CHOICE,
        QuestionType.TRUE_FALSE,
        QuestionType.SHORT_ANSWER,
        QuestionType.NUMERIC,
        QuestionType.FILL_BLANK,
        QuestionType.MATCHING,
    }

    @staticmethod
    def grade_question(*, attempt_question):
        version = (
            attempt_question
            .exam_question
            .question_version
        )

        question_type = version.question_type

        if question_type == QuestionType.ESSAY:
            return (
                ObjectiveGradingService
                ._mark_pending_manual(
                    attempt_question=attempt_question,
                )
            )

        if question_type not in ObjectiveGradingService.AUTO_TYPES:
            raise ValidationError(
                f"Unsupported question type: {question_type}"
            )

        answer = getattr(
            attempt_question,
            "answer",
            None,
        )

        if (
            answer is None
            or not answer.is_answered
        ):
            return (
                ObjectiveGradingService
                ._save_auto_grade(
                    attempt_question=attempt_question,
                    awarded_marks=Decimal("0"),
                    is_correct=False,
                )
            )

        if question_type in {
            QuestionType.SINGLE_CHOICE,
            QuestionType.MULTIPLE_CHOICE,
            QuestionType.TRUE_FALSE,
        }:
            return (
                ObjectiveGradingService
                ._grade_choice(
                    attempt_question=attempt_question,
                    answer=answer,
                )
            )

        if question_type == QuestionType.SHORT_ANSWER:
            return (
                ObjectiveGradingService
                ._grade_short_answer(
                    attempt_question=attempt_question,
                    answer=answer,
                )
            )

        if question_type == QuestionType.NUMERIC:
            return (
                ObjectiveGradingService
                ._grade_numeric(
                    attempt_question=attempt_question,
                    answer=answer,
                )
            )

        if question_type == QuestionType.FILL_BLANK:
            return (
                ObjectiveGradingService
                ._grade_fill_blank(
                    attempt_question=attempt_question,
                    answer=answer,
                )
            )

        if question_type == QuestionType.MATCHING:
            return (
                ObjectiveGradingService
                ._grade_matching(
                    attempt_question=attempt_question,
                    answer=answer,
                )
            )

        raise ValidationError(
            "Question type cannot be auto-graded."
        )

    # =========================================================
    # CHOICE
    # =========================================================

    @staticmethod
    def _grade_choice(
        *,
        attempt_question,
        answer,
    ):
        version = (
            attempt_question
            .exam_question
            .question_version
        )

        correct_ids = set(
            version.options
            .filter(is_correct=True)
            .values_list(
                "id",
                flat=True,
            )
        )

        selected_ids = set(
            answer.selected_options
            .values_list(
                "question_option_id",
                flat=True,
            )
        )

        is_correct = (
            selected_ids == correct_ids
            and bool(correct_ids)
        )

        marks = (
            attempt_question.exam_question.marks
            if is_correct
            else Decimal("0")
        )

        return (
            ObjectiveGradingService
            ._save_auto_grade(
                attempt_question=attempt_question,
                awarded_marks=marks,
                is_correct=is_correct,
            )
        )

    # =========================================================
    # SHORT ANSWER
    # =========================================================

    @staticmethod
    def _grade_short_answer(
        *,
        attempt_question,
        answer,
    ):
        version = (
            attempt_question
            .exam_question
            .question_version
        )

        try:
            definition = (
                version.short_answer_definition
            )
        except ObjectDoesNotExist:
            raise ValidationError(
                "Short-answer definition is missing."
            )

        try:
            submitted = answer.text_response.text
        except ObjectDoesNotExist:
            submitted = ""

        if definition.trim_whitespace:
            submitted = submitted.strip()

        accepted_answers = list(
            definition.accepted_answers
            .values_list(
                "answer",
                flat=True,
            )
        )

        if definition.trim_whitespace:
            accepted_answers = [
                item.strip()
                for item in accepted_answers
            ]

        if not definition.case_sensitive:
            submitted = submitted.casefold()

            accepted_answers = [
                item.casefold()
                for item in accepted_answers
            ]

        is_correct = (
            submitted in accepted_answers
        )

        marks = (
            attempt_question.exam_question.marks
            if is_correct
            else Decimal("0")
        )

        return (
            ObjectiveGradingService
            ._save_auto_grade(
                attempt_question=attempt_question,
                awarded_marks=marks,
                is_correct=is_correct,
            )
        )

    # =========================================================
    # NUMERIC
    # =========================================================

    @staticmethod
    def _grade_numeric(
        *,
        attempt_question,
        answer,
    ):
        version = (
            attempt_question
            .exam_question
            .question_version
        )

        try:
            definition = (
                version.numeric_answer_definition
            )
        except ObjectDoesNotExist:
            raise ValidationError(
                "Numeric answer definition is missing."
            )

        try:
            submitted = (
                answer.numeric_response.value
            )
        except ObjectDoesNotExist:
            submitted = None

        is_correct = False

        if submitted is not None:
            difference = abs(
                submitted
                - definition.expected_value
            )

            is_correct = (
                difference <= definition.tolerance
            )

        marks = (
            attempt_question.exam_question.marks
            if is_correct
            else Decimal("0")
        )

        return (
            ObjectiveGradingService
            ._save_auto_grade(
                attempt_question=attempt_question,
                awarded_marks=marks,
                is_correct=is_correct,
            )
        )

    # =========================================================
    # FILL BLANK
    # Partial credit per blank.
    # =========================================================

    @staticmethod
    def _grade_fill_blank(
        *,
        attempt_question,
        answer,
    ):
        version = (
            attempt_question
            .exam_question
            .question_version
        )

        try:
            definition = (
                version.fill_blank_definition
            )
        except ObjectDoesNotExist:
            raise ValidationError(
                "Fill-blank definition is missing."
            )

        blanks = list(
            definition.blanks
            .prefetch_related(
                "accepted_answers"
            )
            .order_by("position")
        )

        if not blanks:
            raise ValidationError(
                "Fill-blank question has no blanks."
            )

        responses = {
            response.blank_id: response.answer
            for response in (
                answer.blank_responses.all()
            )
        }

        correct_count = 0

        for blank in blanks:
            submitted = responses.get(
                blank.id,
                "",
            ).strip()

            accepted = [
                item.answer.strip()
                for item in blank.accepted_answers.all()
            ]

            if not definition.case_sensitive:
                submitted = submitted.casefold()

                accepted = [
                    item.casefold()
                    for item in accepted
                ]

            if submitted and submitted in accepted:
                correct_count += 1

        ratio = (
            Decimal(correct_count)
            / Decimal(len(blanks))
        )

        max_marks = (
            attempt_question.exam_question.marks
        )

        awarded = (
            max_marks * ratio
        ).quantize(
            ObjectiveGradingService.TWO_PLACES,
            rounding=ROUND_HALF_UP,
        )

        return (
            ObjectiveGradingService
            ._save_auto_grade(
                attempt_question=attempt_question,
                awarded_marks=awarded,
                is_correct=(
                    correct_count == len(blanks)
                ),
            )
        )

    # =========================================================
    # MATCHING
    # Partial credit per correctly matched pair.
    # =========================================================

    @staticmethod
    def _grade_matching(
        *,
        attempt_question,
        answer,
    ):
        version = (
            attempt_question
            .exam_question
            .question_version
        )

        try:
            definition = (
                version.matching_definition
            )
        except ObjectDoesNotExist:
            raise ValidationError(
                "Matching definition is missing."
            )

        pairs = list(
            definition.pairs.all()
        )

        if not pairs:
            raise ValidationError(
                "Matching question has no pairs."
            )

        submitted = {
            response.left_pair_id:
                response.selected_right_pair_id
            for response in (
                answer.matching_responses.all()
            )
        }

        correct_count = 0

        for pair in pairs:
            selected_right_id = (
                submitted.get(pair.id)
            )

            # Correct pair means left and right came
            # from the same canonical MatchingPair.
            if selected_right_id == pair.id:
                correct_count += 1

        ratio = (
            Decimal(correct_count)
            / Decimal(len(pairs))
        )

        max_marks = (
            attempt_question.exam_question.marks
        )

        awarded = (
            max_marks * ratio
        ).quantize(
            ObjectiveGradingService.TWO_PLACES,
            rounding=ROUND_HALF_UP,
        )

        return (
            ObjectiveGradingService
            ._save_auto_grade(
                attempt_question=attempt_question,
                awarded_marks=awarded,
                is_correct=(
                    correct_count == len(pairs)
                ),
            )
        )

    # =========================================================
    # SAVE AUTO GRADE
    # =========================================================

    @staticmethod
    def _save_auto_grade(
        *,
        attempt_question,
        awarded_marks,
        is_correct,
    ):
        max_marks = (
            attempt_question
            .exam_question
            .marks
        )

        grade, _ = (
            AttemptQuestionGrade.objects
            .update_or_create(
                attempt_question=attempt_question,
                defaults={
                    "awarded_marks":
                        awarded_marks,
                    "max_marks":
                        max_marks,
                    "is_correct":
                        is_correct,
                    "status":
                        QuestionGradingStatus.AUTO_GRADED,
                    "grading_method":
                        GradingMethod.AUTO,
                    "graded_by":
                        None,
                    "graded_at":
                        timezone.now(),
                },
            )
        )

        return grade

    # =========================================================
    # ESSAY PENDING MANUAL
    # =========================================================

    @staticmethod
    def _mark_pending_manual(
        *,
        attempt_question,
    ):
        max_marks = (
            attempt_question
            .exam_question
            .marks
        )

        grade, _ = (
            AttemptQuestionGrade.objects
            .update_or_create(
                attempt_question=attempt_question,
                defaults={
                    "awarded_marks":
                        Decimal("0"),
                    "max_marks":
                        max_marks,
                    "is_correct":
                        None,
                    "status":
                        QuestionGradingStatus.PENDING_MANUAL,
                    "grading_method":
                        GradingMethod.MANUAL,
                    "graded_by":
                        None,
                    "graded_at":
                        None,
                },
            )
        )

        return grade