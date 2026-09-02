from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError

from cbt.models import QuestionType
from cbt.services import StudentAnswerService


class AnswerSaveSerializer(serializers.Serializer):
    """
    Type-aware serializer for saving student responses across all question types.
    """
    option_ids = serializers.ListField(
        child=serializers.CharField(), required=False, allow_empty=True
    )
    text = serializers.CharField(required=False, allow_blank=True)
    value = serializers.CharField(required=False, allow_blank=True)
    responses = serializers.DictField(
        child=serializers.CharField(allow_blank=True), required=False
    )
    matches = serializers.DictField(
        child=serializers.UUIDField(), required=False
    )
    event_id = serializers.UUIDField(required=False)
    client_id = serializers.UUIDField(required=False)
    client_sequence = serializers.IntegerField(required=False, min_value=1)
    base_revision = serializers.IntegerField(required=False, min_value=0, allow_null=True)
    client_timestamp = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, attrs):
        supplied = {name for name in ("event_id", "client_id", "client_sequence") if name in attrs}
        if supplied and len(supplied) != 3:
            raise serializers.ValidationError(
                "event_id, client_id and client_sequence must be supplied together."
            )
        return attrs

    def _event_metadata(self):
        return {
            name: self.validated_data.get(name)
            for name in (
                "event_id", "client_id", "client_sequence",
                "base_revision", "client_timestamp",
            )
        }

    def save_answer(self, attempt_question, student=None):
        q_type = (
            attempt_question.published_question.question_type
            if attempt_question.published_question_id
            else attempt_question.exam_question.question_version.question_type
        )

        try:
            if q_type in {QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE, QuestionType.TRUE_FALSE}:
                option_ids = self.validated_data.get("option_ids", [])
                payload = {"option_ids": option_ids}

            elif q_type in {QuestionType.SHORT_ANSWER, QuestionType.ESSAY}:
                text = self.validated_data.get("text", "")
                payload = {"text": text}

            elif q_type == QuestionType.NUMERIC:
                value = self.validated_data.get("value", "")
                payload = {"value": value}

            elif q_type == QuestionType.FILL_BLANK:
                responses = self.validated_data.get("responses", {})
                payload = {"responses": responses}

            elif q_type == QuestionType.MATCHING:
                matches = self.validated_data.get("matches", {})
                payload = {"matches": matches}

            else:
                raise serializers.ValidationError(f"Unsupported question type '{q_type}'.")

            return StudentAnswerService.apply_answer_event(
                attempt_question=attempt_question,
                operation="SET",
                payload=payload,
                student=student,
                **self._event_metadata(),
            )

        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                exc.message_dict if hasattr(exc, "message_dict") else exc.messages
            )

    def clear_answer(self, attempt_question, student=None):
        try:
            return StudentAnswerService.apply_answer_event(
                attempt_question=attempt_question,
                operation="CLEAR",
                payload={},
                student=student,
                **self._event_metadata(),
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                exc.message_dict if hasattr(exc, "message_dict") else exc.messages
            )


class SubmissionSerializer(serializers.Serializer):
    submission_id = serializers.UUIDField(required=False)


class FlagQuestionSerializer(serializers.Serializer):
    flagged = serializers.BooleanField()

    def save_flag(self, attempt_question):
        return StudentAnswerService.set_flagged(
            attempt_question=attempt_question,
            flagged=self.validated_data["flagged"],
        )
