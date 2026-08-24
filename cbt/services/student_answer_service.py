from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

from ..models import (
    ExamAttemptStatus,
    QuestionType,
    StudentAnswer,
    StudentChoiceAnswer,
    StudentTextAnswer,
    StudentNumericAnswer,
    StudentFillBlankAnswer,
    StudentMatchingAnswer,
)


class StudentAnswerService:

    # =========================================================
    # COMMON HELPERS
    # =========================================================

    @staticmethod
    def ensure_answerable(attempt_question):
        attempt = attempt_question.attempt

        if attempt.status != ExamAttemptStatus.IN_PROGRESS:
            raise ValidationError(
                "Answers can only be changed while "
                "the attempt is in progress."
            )

        if timezone.now() >= attempt.expires_at:
            raise ValidationError(
                "This exam attempt has expired."
            )

    @staticmethod
    def _get_version(attempt_question):
        return (
            attempt_question
            .exam_question
            .question_version
        )

    @staticmethod
    def _get_answer(attempt_question):
        answer, _ = StudentAnswer.objects.get_or_create(
            attempt_question=attempt_question
        )

        return answer

    @staticmethod
    def _set_answer_state(
        *,
        answer,
        is_answered,
    ):
        answer.is_answered = is_answered

        answer.answered_at = (
            timezone.now()
            if is_answered
            else None
        )

        answer.save(
            update_fields=[
                "is_answered",
                "answered_at",
                "updated_at",
            ]
        )

        StudentAnswerService._touch_attempt(
            answer.attempt_question.attempt
        )

    @staticmethod
    def _touch_attempt(attempt):
        attempt.last_activity_at = timezone.now()

        attempt.save(
            update_fields=[
                "last_activity_at",
                "updated_at",
            ]
        )

    # =========================================================
    # CHOICE ANSWERS
    # SINGLE_CHOICE
    # MULTIPLE_CHOICE
    # TRUE_FALSE
    # =========================================================

    @staticmethod
    @transaction.atomic
    def save_choice_answer(
        *,
        attempt_question,
        option_ids,
    ):
        StudentAnswerService.ensure_answerable(
            attempt_question
        )

        version = StudentAnswerService._get_version(
            attempt_question
        )

        if version.question_type not in {
            QuestionType.SINGLE_CHOICE,
            QuestionType.MULTIPLE_CHOICE,
            QuestionType.TRUE_FALSE,
        }:
            raise ValidationError(
                "This question does not accept option answers."
            )

        option_ids = list(
            dict.fromkeys(option_ids or [])
        )

        options = list(
            version.options.filter(
                id__in=option_ids
            )
        )

        if len(options) != len(option_ids):
            raise ValidationError(
                "One or more selected options are invalid."
            )

        if (
            version.question_type
            in {
                QuestionType.SINGLE_CHOICE,
                QuestionType.TRUE_FALSE,
            }
            and len(options) > 1
        ):
            raise ValidationError(
                "Only one option may be selected."
            )

        answer = StudentAnswerService._get_answer(
            attempt_question
        )

        # Replace existing selection.
        answer.selected_options.all().delete()

        StudentChoiceAnswer.objects.bulk_create(
            [
                StudentChoiceAnswer(
                    student_answer=answer,
                    question_option=option,
                )
                for option in options
            ]
        )

        StudentAnswerService._set_answer_state(
            answer=answer,
            is_answered=bool(options),
        )

        return answer

    # =========================================================
    # TEXT ANSWERS
    # SHORT_ANSWER
    # ESSAY
    # =========================================================

    @staticmethod
    @transaction.atomic
    def save_text_answer(
        *,
        attempt_question,
        text,
    ):
        StudentAnswerService.ensure_answerable(
            attempt_question
        )

        version = StudentAnswerService._get_version(
            attempt_question
        )

        if version.question_type not in {
            QuestionType.SHORT_ANSWER,
            QuestionType.ESSAY,
        }:
            raise ValidationError(
                "This question does not accept a text answer."
            )

        text = text or ""

        answer = StudentAnswerService._get_answer(
            attempt_question
        )

        if not text.strip():
            StudentTextAnswer.objects.filter(
                student_answer=answer
            ).delete()

            StudentAnswerService._set_answer_state(
                answer=answer,
                is_answered=False,
            )

            return answer

        StudentTextAnswer.objects.update_or_create(
            student_answer=answer,
            defaults={
                "text": text,
            },
        )

        StudentAnswerService._set_answer_state(
            answer=answer,
            is_answered=True,
        )

        return answer

    # =========================================================
    # NUMERIC
    # =========================================================

    @staticmethod
    @transaction.atomic
    def save_numeric_answer(
        *,
        attempt_question,
        value,
    ):
        StudentAnswerService.ensure_answerable(
            attempt_question
        )

        version = StudentAnswerService._get_version(
            attempt_question
        )

        if version.question_type != QuestionType.NUMERIC:
            raise ValidationError(
                "This question does not accept "
                "a numeric answer."
            )

        answer = StudentAnswerService._get_answer(
            attempt_question
        )

        # Empty value means clear the response.
        if value is None or value == "":
            StudentNumericAnswer.objects.filter(
                student_answer=answer
            ).delete()

            StudentAnswerService._set_answer_state(
                answer=answer,
                is_answered=False,
            )

            return answer

        try:
            numeric_value = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError(
                "A valid numeric value is required."
            )

        StudentNumericAnswer.objects.update_or_create(
            student_answer=answer,
            defaults={
                "value": numeric_value,
            },
        )

        StudentAnswerService._set_answer_state(
            answer=answer,
            is_answered=True,
        )

        return answer

    # =========================================================
    # FILL IN THE BLANK
    #
    # Expected input:
    #
    # responses = {
    #     blank_id: "answer",
    #     blank_id: "answer",
    # }
    #
    # =========================================================

    @staticmethod
    @transaction.atomic
    def save_fill_blank_answer(
        *,
        attempt_question,
        responses,
    ):
        StudentAnswerService.ensure_answerable(
            attempt_question
        )

        version = StudentAnswerService._get_version(
            attempt_question
        )

        if version.question_type != QuestionType.FILL_BLANK:
            raise ValidationError(
                "This question does not accept "
                "fill-in-the-blank answers."
            )

        try:
            definition = version.fill_blank_definition
        except ObjectDoesNotExist:
            raise ValidationError(
                "This question does not have a "
                "fill-in-the-blank definition."
            )

        responses = responses or {}

        try:
            submitted_blank_ids = {
                int(blank_id)
                for blank_id in responses.keys()
            }
        except (TypeError, ValueError):
            raise ValidationError(
                "One or more blank IDs are invalid."
            )

        valid_blanks = {
            blank.id: blank
            for blank in definition.blanks.filter(
                id__in=submitted_blank_ids
            )
        }

        if len(valid_blanks) != len(
            submitted_blank_ids
        ):
            raise ValidationError(
                "One or more blanks do not belong "
                "to this question."
            )

        answer = StudentAnswerService._get_answer(
            attempt_question
        )

        # Replace the current response set.
        answer.blank_responses.all().delete()

        response_objects = []

        for raw_blank_id, value in responses.items():
            blank_id = int(raw_blank_id)

            value = (
                str(value)
                if value is not None
                else ""
            )

            # Empty blanks are simply unanswered.
            if not value.strip():
                continue

            response_objects.append(
                StudentFillBlankAnswer(
                    student_answer=answer,
                    blank=valid_blanks[blank_id],
                    answer=value,
                )
            )

        StudentFillBlankAnswer.objects.bulk_create(
            response_objects
        )

        StudentAnswerService._set_answer_state(
            answer=answer,
            is_answered=bool(response_objects),
        )

        return answer

    # =========================================================
    # MATCHING
    #
    # Expected input:
    #
    # matches = {
    #     left_pair_id: selected_right_pair_id,
    #     left_pair_id: selected_right_pair_id,
    # }
    #
    # =========================================================

    @staticmethod
    @transaction.atomic
    def save_matching_answer(
        *,
        attempt_question,
        matches,
    ):
        StudentAnswerService.ensure_answerable(
            attempt_question
        )

        version = StudentAnswerService._get_version(
            attempt_question
        )

        if version.question_type != QuestionType.MATCHING:
            raise ValidationError(
                "This question does not accept "
                "matching answers."
            )

        try:
            definition = version.matching_definition
        except ObjectDoesNotExist:
            raise ValidationError(
                "This question does not have "
                "a matching definition."
            )

        matches = matches or {}

        try:
            left_ids = {
                int(pair_id)
                for pair_id in matches.keys()
            }

            right_ids = {
                int(pair_id)
                for pair_id in matches.values()
                if pair_id not in {
                    None,
                    "",
                }
            }

        except (TypeError, ValueError):
            raise ValidationError(
                "One or more matching pair IDs are invalid."
            )

        all_pair_ids = left_ids | right_ids

        valid_pairs = {
            pair.id: pair
            for pair in definition.pairs.filter(
                id__in=all_pair_ids
            )
        }

        if not all_pair_ids.issubset(
            valid_pairs.keys()
        ):
            raise ValidationError(
                "One or more matching items do not "
                "belong to this question."
            )

        answer = StudentAnswerService._get_answer(
            attempt_question
        )

        answer.matching_responses.all().delete()

        response_objects = []

        selected_right_ids = set()

        for raw_left_id, raw_right_id in matches.items():
            left_id = int(raw_left_id)

            # Allow clearing/unmatched left items.
            if raw_right_id in {
                None,
                "",
            }:
                continue

            right_id = int(raw_right_id)

            if right_id in selected_right_ids:
                raise ValidationError(
                    "The same right-side item cannot "
                    "be matched more than once."
                )

            selected_right_ids.add(right_id)

            response_objects.append(
                StudentMatchingAnswer(
                    student_answer=answer,
                    left_pair=valid_pairs[left_id],
                    selected_right_pair=valid_pairs[
                        right_id
                    ],
                )
            )

        StudentMatchingAnswer.objects.bulk_create(
            response_objects
        )

        StudentAnswerService._set_answer_state(
            answer=answer,
            is_answered=bool(response_objects),
        )

        return answer

    # =========================================================
    # CLEAR ANSWER
    # =========================================================

    @staticmethod
    @transaction.atomic
    def clear_answer(
        *,
        attempt_question,
    ):
        StudentAnswerService.ensure_answerable(
            attempt_question
        )

        try:
            answer = attempt_question.answer
        except StudentAnswer.DoesNotExist:
            StudentAnswerService._touch_attempt(
                attempt_question.attempt
            )
            return None

        # Choice
        answer.selected_options.all().delete()

        # Text
        StudentTextAnswer.objects.filter(
            student_answer=answer
        ).delete()

        # Numeric
        StudentNumericAnswer.objects.filter(
            student_answer=answer
        ).delete()

        # Fill blank
        answer.blank_responses.all().delete()

        # Matching
        answer.matching_responses.all().delete()

        answer.is_answered = False
        answer.answered_at = None

        answer.save(
            update_fields=[
                "is_answered",
                "answered_at",
                "updated_at",
            ]
        )

        StudentAnswerService._touch_attempt(
            attempt_question.attempt
        )

        return answer

    # =========================================================
    # FLAG / UNFLAG
    #
    # Flagging belongs to AttemptQuestion,
    # not StudentAnswer.
    # =========================================================

    @staticmethod
    @transaction.atomic
    def set_flagged(
        *,
        attempt_question,
        flagged,
    ):
        StudentAnswerService.ensure_answerable(
            attempt_question
        )

        attempt_question.is_flagged = bool(flagged)

        attempt_question.save(
            update_fields=[
                "is_flagged",
            ]
        )

        StudentAnswerService._touch_attempt(
            attempt_question.attempt
        )

        return attempt_question