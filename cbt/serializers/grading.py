from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError

from cbt.models import (
    AttemptQuestionGrade,
    AttemptGrade,
    AttemptQuestion,
)
from cbt.services import ManualGradingService, ResultPostingService


class AttemptQuestionGradeSerializer(serializers.ModelSerializer):
    graded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = AttemptQuestionGrade
        fields = [
            "id",
            "attempt_question",
            "awarded_marks",
            "max_marks",
            "is_correct",
            "status",
            "grading_method",
            "feedback",
            "graded_by",
            "graded_by_name",
            "graded_at",
            "created_at",
        ]
        read_only_fields = [
            "attempt_question",
            "awarded_marks",
            "max_marks",
            "is_correct",
            "status",
            "grading_method",
            "graded_by",
            "graded_at",
            "created_at",
        ]

    def get_graded_by_name(self, obj):
        if obj.graded_by and obj.graded_by.user:
            return obj.graded_by.user.get_full_name()
        return ""


class AttemptGradeSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    admission_number = serializers.SerializerMethodField()
    exam_title = serializers.CharField(source="attempt.cbt_exam.title", read_only=True)
    question_grades = serializers.SerializerMethodField()

    class Meta:
        model = AttemptGrade
        fields = [
            "id",
            "attempt",
            "student_name",
            "admission_number",
            "exam_title",
            "status",
            "raw_score",
            "total_marks",
            "percentage",
            "normalized_score",
            "graded_at",
            "posted_at",
            "question_grades",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "attempt",
            "status",
            "raw_score",
            "total_marks",
            "percentage",
            "normalized_score",
            "graded_at",
            "posted_at",
            "created_at",
            "updated_at",
        ]

    def get_student_name(self, obj):
        user = getattr(obj.attempt.student, "user", None)
        return user.get_full_name() if user else ""

    def get_admission_number(self, obj):
        return getattr(obj.attempt.student, "admission_number", "")

    def get_question_grades(self, obj):
        # Only include per-question grades for teachers/admins
        user = self.context.get("request", None) and self.context["request"].user
        if not user or getattr(user, "is_student", False):
            return None

        grades = AttemptQuestionGrade.objects.filter(
            attempt_question__attempt=obj.attempt
        ).select_related("attempt_question", "graded_by__user")
        return AttemptQuestionGradeSerializer(grades, many=True).data


class ManualEssayGradeSerializer(serializers.Serializer):
    marks = serializers.DecimalField(max_digits=8, decimal_places=2)
    feedback = serializers.CharField(required=False, allow_blank=True, default="")

    def grade(self, attempt_question):
        user = self.context["request"].user
        try:
            return ManualGradingService.grade_essay(
                attempt_question=attempt_question,
                marks=self.validated_data["marks"],
                graded_by=user,
                feedback=self.validated_data.get("feedback", ""),
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                exc.message_dict if hasattr(exc, "message_dict") else exc.messages
            )


class PendingEssayGradingSerializer(serializers.Serializer):
    attempt_question_id = serializers.IntegerField(source="id")
    attempt_id = serializers.IntegerField(source="attempt.id")
    student_name = serializers.SerializerMethodField()
    admission_number = serializers.SerializerMethodField()
    exam_title = serializers.CharField(source="attempt.cbt_exam.title")
    subject_name = serializers.CharField(source="attempt.cbt_exam.subject.name")
    question_text = serializers.CharField(source="exam_question.question_version.text")
    submitted_text = serializers.SerializerMethodField()
    max_marks = serializers.SerializerMethodField()
    submitted_at = serializers.DateTimeField(source="attempt.submitted_at")
    def get_student_name(self, obj):
        user = getattr(obj.attempt.student, "user", None)
        return user.get_full_name() if user else ""

    def get_admission_number(self, obj):
        return getattr(obj.attempt.student, "admission_number", "")

    def get_max_marks(self, obj):
        return str(obj.exam_question.marks)

    def get_submitted_text(self, obj):
        if hasattr(obj, "answer") and hasattr(obj.answer, "text_response"):
            try:
                return obj.answer.text_response.text
            except Exception:
                return ""
        return ""


class ManualEssayGradeResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()
    awarded_marks = serializers.DecimalField(max_digits=8, decimal_places=2)
    status = serializers.CharField()
