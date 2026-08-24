from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError

from academic.models import Subject, Topic, SubTopic, GradeLevel
from cbt.models import (
    QuestionBank,
    Question,
    QuestionVersion,
    QuestionOption,
    QuestionAttachment,
    QuestionLearningObjective,
    QuestionReview,
    QuestionType,
    QuestionDifficulty,
    QuestionStatus,
)
from cbt.services import QuestionBankService, CBTActorService


class QuestionOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionOption
        fields = [
            "id",
            "text",
            "is_correct",
            "feedback",
            "order",
        ]


class QuestionAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionAttachment
        fields = [
            "id",
            "question_version",
            "file",
            "caption",
            "order",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class QuestionLearningObjectiveSerializer(serializers.ModelSerializer):
    objective_description = serializers.CharField(
        source="learning_objective.description", read_only=True
    )

    class Meta:
        model = QuestionLearningObjective
        fields = [
            "id",
            "question_version",
            "learning_objective",
            "objective_description",
            "is_primary",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class QuestionReviewSerializer(serializers.ModelSerializer):
    reviewed_by_name = serializers.CharField(
        source="reviewed_by.user.get_full_name", read_only=True, default=""
    )

    class Meta:
        model = QuestionReview
        fields = [
            "id",
            "question_version",
            "reviewed_by",
            "reviewed_by_name",
            "decision",
            "comments",
            "reviewed_at",
        ]
        read_only_fields = ["reviewed_by", "reviewed_at"]


class QuestionVersionSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(
        source="created_by.user.get_full_name", read_only=True, default=""
    )
    options = QuestionOptionSerializer(many=True, read_only=True)
    attachments = QuestionAttachmentSerializer(many=True, read_only=True)
    objective_alignments = QuestionLearningObjectiveSerializer(many=True, read_only=True)
    reviews = QuestionReviewSerializer(many=True, read_only=True)

    class Meta:
        model = QuestionVersion
        fields = [
            "id",
            "question",
            "version",
            "text",
            "instructions",
            "explanation",
            "created_by",
            "created_by_name",
            "options",
            "attachments",
            "objective_alignments",
            "reviews",
            "created_at",
        ]
        read_only_fields = ["version", "created_by", "created_at"]


class QuestionBankSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    created_by_name = serializers.CharField(
        source="created_by.user.get_full_name", read_only=True, default=""
    )

    class Meta:
        model = QuestionBank
        fields = [
            "id",
            "name",
            "subject",
            "subject_name",
            "description",
            "is_active",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_by", "created_at", "updated_at"]

    def create(self, validated_data):
        user = self.context["request"].user
        try:
            teacher = CBTActorService.resolve_teacher(user)
        except DjangoValidationError:
            teacher = None
        validated_data["created_by"] = teacher
        return super().create(validated_data)


class QuestionListSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    topic_name = serializers.CharField(source="topic.name", read_only=True, default="")
    subtopic_name = serializers.CharField(source="subtopic.name", read_only=True, default="")
    created_by_name = serializers.CharField(
        source="created_by.user.get_full_name", read_only=True, default=""
    )
    text = serializers.CharField(source="current_version.text", read_only=True, default="")
    current_version_number = serializers.IntegerField(
        source="current_version.version", read_only=True, default=1
    )

    class Meta:
        model = Question
        fields = [
            "id",
            "bank",
            "subject",
            "subject_name",
            "topic",
            "topic_name",
            "subtopic",
            "subtopic_name",
            "question_type",
            "difficulty",
            "default_marks",
            "status",
            "current_version",
            "current_version_number",
            "text",
            "created_by",
            "created_by_name",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "status",
            "current_version",
            "created_by",
            "created_at",
            "updated_at",
        ]


class QuestionDetailSerializer(QuestionListSerializer):
    current_version_detail = QuestionVersionSerializer(
        source="current_version", read_only=True
    )
    versions = QuestionVersionSerializer(many=True, read_only=True)
    grade_levels = serializers.PrimaryKeyRelatedField(
        many=True, read_only=True
    )

    class Meta(QuestionListSerializer.Meta):
        fields = QuestionListSerializer.Meta.fields + [
            "grade_levels",
            "current_version_detail",
            "versions",
        ]


class QuestionCreateSerializer(serializers.Serializer):
    bank = serializers.PrimaryKeyRelatedField(
        queryset=QuestionBank.objects.filter(is_active=True), required=False, allow_null=True
    )
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all())
    grade_levels = serializers.PrimaryKeyRelatedField(
        queryset=GradeLevel.objects.all(), many=True, required=False
    )
    topic = serializers.PrimaryKeyRelatedField(
        queryset=Topic.objects.all(), required=False, allow_null=True
    )
    subtopic = serializers.PrimaryKeyRelatedField(
        queryset=SubTopic.objects.all(), required=False, allow_null=True
    )
    question_type = serializers.ChoiceField(choices=QuestionType.choices)
    difficulty = serializers.ChoiceField(
        choices=QuestionDifficulty.choices, default=QuestionDifficulty.MEDIUM
    )
    default_marks = serializers.DecimalField(
        max_digits=5, decimal_places=2, default=1.00
    )
    text = serializers.CharField()
    instructions = serializers.CharField(required=False, allow_blank=True, default="")
    explanation = serializers.CharField(required=False, allow_blank=True, default="")
    options = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    answer_definition = serializers.DictField(required=False, default=dict)

    def create(self, validated_data):
        user = self.context["request"].user
        teacher = CBTActorService.resolve_teacher(user)
        try:
            return QuestionBankService.create_question(
                subject=validated_data["subject"],
                grade_levels=validated_data.get("grade_levels", []),
                question_type=validated_data["question_type"],
                text=validated_data["text"],
                created_by=teacher,
                bank=validated_data.get("bank"),
                topic=validated_data.get("topic"),
                subtopic=validated_data.get("subtopic"),
                difficulty=validated_data.get("difficulty", QuestionDifficulty.MEDIUM),
                default_marks=validated_data.get("default_marks", 1.00),
                instructions=validated_data.get("instructions", ""),
                explanation=validated_data.get("explanation", ""),
                options=validated_data.get("options"),
                answer_definition=validated_data.get("answer_definition"),
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)


class QuestionNewVersionSerializer(serializers.Serializer):
    text = serializers.CharField()
    instructions = serializers.CharField(required=False, allow_blank=True, default="")
    explanation = serializers.CharField(required=False, allow_blank=True, default="")
    options = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    answer_definition = serializers.DictField(required=False, default=dict)

    def save_version(self, question):
        user = self.context["request"].user
        teacher = CBTActorService.resolve_teacher(user)
        try:
            return QuestionBankService.create_new_version(
                question=question,
                text=self.validated_data["text"],
                created_by=teacher,
                instructions=self.validated_data.get("instructions", ""),
                explanation=self.validated_data.get("explanation", ""),
                options=self.validated_data.get("options"),
                answer_definition=self.validated_data.get("answer_definition"),
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
