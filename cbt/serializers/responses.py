from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError

from cbt.models import QuestionType
from cbt.services import StudentAnswerService


class AnswerSaveSerializer(serializers.Serializer):
    """
    Type-aware serializer for saving student responses across all question types.
    """
    option_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True
    )
    text = serializers.CharField(required=False, allow_blank=True)
    value = serializers.CharField(required=False, allow_blank=True)
    responses = serializers.DictField(
        child=serializers.CharField(allow_blank=True), required=False
    )
    matches = serializers.DictField(
        child=serializers.IntegerField(), required=False
    )

    def save_answer(self, attempt_question):
        version = attempt_question.exam_question.question_version
        q_type = version.question.question_type

        try:
            if q_type in {QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE, QuestionType.TRUE_FALSE}:
                option_ids = self.validated_data.get("option_ids", [])
                return StudentAnswerService.save_choice_answer(
                    attempt_question=attempt_question,
                    option_ids=option_ids,
                )

            elif q_type in {QuestionType.SHORT_ANSWER, QuestionType.ESSAY}:
                text = self.validated_data.get("text", "")
                return StudentAnswerService.save_text_answer(
                    attempt_question=attempt_question,
                    text=text,
                )

            elif q_type == QuestionType.NUMERIC:
                value = self.validated_data.get("value", "")
                return StudentAnswerService.save_numeric_answer(
                    attempt_question=attempt_question,
                    value=value,
                )

            elif q_type == QuestionType.FILL_BLANK:
                responses = self.validated_data.get("responses", {})
                return StudentAnswerService.save_fill_blank_answer(
                    attempt_question=attempt_question,
                    responses=responses,
                )

            elif q_type == QuestionType.MATCHING:
                matches = self.validated_data.get("matches", {})
                return StudentAnswerService.save_matching_answer(
                    attempt_question=attempt_question,
                    matches=matches,
                )

            else:
                raise serializers.ValidationError(f"Unsupported question type '{q_type}'.")

        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                exc.message_dict if hasattr(exc, "message_dict") else exc.messages
            )


class FlagQuestionSerializer(serializers.Serializer):
    flagged = serializers.BooleanField()

    def save_flag(self, attempt_question):
        return StudentAnswerService.set_flagged(
            attempt_question=attempt_question,
            flagged=self.validated_data["flagged"],
        )
