from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError

from academic.models import Subject, ClassRoom, AllocatedSubject
from examination.models import AssessmentSession, AssessmentComponent
from cbt.models import (
    CBTExam,
    CBTExamStatus,
    ExamBlueprint,
    BlueprintRule,
    ExamQuestion,
    QuestionType,
    QuestionDifficulty,
)
from cbt.serializers.question_bank import QuestionVersionSerializer
from cbt.services import CBTActorService


class BlueprintRuleSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source="topic.name", read_only=True, default="")
    subtopic_name = serializers.CharField(source="subtopic.name", read_only=True, default="")

    class Meta:
        model = BlueprintRule
        fields = [
            "id",
            "blueprint",
            "topic",
            "topic_name",
            "subtopic",
            "subtopic_name",
            "learning_objective",
            "question_type",
            "difficulty",
            "question_count",
            "order",
        ]
        read_only_fields = ["blueprint"]


class ExamBlueprintSerializer(serializers.ModelSerializer):
    rules = BlueprintRuleSerializer(many=True, read_only=True)
    total_questions = serializers.IntegerField(read_only=True)
    generated_question_count = serializers.IntegerField(read_only=True)
    is_generated = serializers.BooleanField(read_only=True)

    class Meta:
        model = ExamBlueprint
        fields = [
            "id",
            "cbt_exam",
            "is_locked",
            "total_questions",
            "generated_question_count",
            "is_generated",
            "rules",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "cbt_exam",
            "is_locked",
            "total_questions",
            "generated_question_count",
            "is_generated",
            "created_at",
            "updated_at",
        ]


class ExamQuestionManagementSerializer(serializers.ModelSerializer):
    question_type = serializers.CharField(
        source="question_version.question_type", read_only=True
    )
    question_text = serializers.CharField(
        source="question_version.text", read_only=True
    )
    question_version_detail = QuestionVersionSerializer(
        source="question_version", read_only=True
    )

    class Meta:
        model = ExamQuestion
        fields = [
            "id",
            "cbt_exam",
            "question_version",
            "question_type",
            "question_text",
            "marks",
            "order",
            "question_version_detail",
            "created_at",
        ]
        read_only_fields = ["cbt_exam", "created_at"]


class CBTExamManagementSerializer(serializers.ModelSerializer):
    session_name = serializers.CharField(source="session.name", read_only=True)
    component_name = serializers.CharField(source="component.name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    classroom_name = serializers.CharField(source="classroom.__str__", read_only=True)
    created_by_name = serializers.CharField(
        source="created_by.user.get_full_name", read_only=True, default=""
    )
    blueprint = ExamBlueprintSerializer(read_only=True)
    exam_questions = ExamQuestionManagementSerializer(many=True, read_only=True)
    question_count = serializers.IntegerField(source="exam_questions.count", read_only=True)
    total_marks = serializers.SerializerMethodField()

    class Meta:
        model = CBTExam
        fields = [
            "id",
            "title",
            "session",
            "session_name",
            "component",
            "component_name",
            "subject",
            "subject_name",
            "classroom",
            "classroom_name",
            "duration_minutes",
            "total_marks",
            "shuffle_questions",
            "shuffle_options",
            "allow_back_navigation",
            "auto_submit",
            "instructions",
            "status",
            "created_by",
            "created_by_name",
            "blueprint",
            "exam_questions",
            "question_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "status",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_total_marks(self, obj):
        total = sum(q.marks for q in obj.exam_questions.all())
        return str(total) if total else "0.00"


class CBTExamCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CBTExam
        fields = [
            "id",
            "title",
            "session",
            "component",
            "subject",
            "classroom",
            "duration_minutes",
            "instructions",
            "shuffle_questions",
            "shuffle_options",
            "allow_back_navigation",
            "auto_submit",
        ]

    def validate(self, attrs):
        user = self.context["request"].user

        # Non-admin teachers must be allocated to the subject and classroom
        if not (user.is_superuser or user.is_staff or getattr(user, "is_admin", False)):
            try:
                teacher = CBTActorService.resolve_teacher(user)
            except DjangoValidationError:
                teacher = None

            if teacher:
                is_allocated = AllocatedSubject.objects.filter(
                    teacher_name=teacher,
                    subject=attrs["subject"],
                    class_room=attrs["classroom"],
                ).exists()
                if not is_allocated:
                    raise serializers.ValidationError(
                        "You are not allocated to teach this subject in this classroom."
                    )

        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        try:
            teacher = CBTActorService.resolve_teacher(user)
        except DjangoValidationError:
            teacher = None

        validated_data["created_by"] = teacher
        validated_data["status"] = CBTExamStatus.DRAFT
        return super().create(validated_data)


class StudentAvailableExamSerializer(serializers.ModelSerializer):
    """
    Student-safe exam serializer.
    Hides all blueprint internals, raw questions, bank metadata, and answer keys.
    """
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    classroom_name = serializers.CharField(source="classroom.__str__", read_only=True)
    question_count = serializers.IntegerField(source="exam_questions.count", read_only=True)
    total_marks = serializers.SerializerMethodField()
    attempt_status = serializers.SerializerMethodField()
    has_active_attempt = serializers.SerializerMethodField()

    class Meta:
        model = CBTExam
        fields = [
            "id",
            "title",
            "subject_name",
            "classroom_name",
            "duration_minutes",
            "total_marks",
            "question_count",
            "instructions",
            "status",
            "has_active_attempt",
            "attempt_status",
            "created_at",
        ]

    def get_total_marks(self, obj):
        total = sum(q.marks for q in obj.exam_questions.all())
        return str(total) if total else "0.00"

    def get_attempt_status(self, obj):
        user = getattr(self.context.get("request", None), "user", None)
        if not user:
            return None
        try:
            student = CBTActorService.resolve_student(user)
        except DjangoValidationError:
            return None

        last_attempt = obj.attempts.filter(student=student).order_by("-started_at").first()
        return last_attempt.status if last_attempt else None

    def get_has_active_attempt(self, obj):
        user = getattr(self.context.get("request", None), "user", None)
        if not user:
            return False
        try:
            student = CBTActorService.resolve_student(user)
        except DjangoValidationError:
            return False

        from cbt.models import ExamAttemptStatus
        return obj.attempts.filter(
            student=student,
            status=ExamAttemptStatus.IN_PROGRESS,
        ).exists()
