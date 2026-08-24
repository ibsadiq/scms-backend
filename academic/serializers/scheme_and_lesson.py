from rest_framework import serializers
from academic.models import (
    SchemeOfWork,
    SchemeOfWorkItem,
    LessonPlan,
    LessonDelivery,
    LessonPlanMaterial,
)


class RejectionSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=True, allow_blank=False)


class SchemeOfWorkItemSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source="curriculum_topic.topic.name", read_only=True)

    class Meta:
        model = SchemeOfWorkItem
        fields = [
            "id",
            "scheme",
            "week_number",
            "curriculum_topic",
            "topic_name",
            "subtopics",
            "learning_objectives",
            "title",
            "notes",
            "order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class SchemeOfWorkSerializer(serializers.ModelSerializer):
    items = SchemeOfWorkItemSerializer(many=True, read_only=True)
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True)
    subject_name = serializers.CharField(source="curriculum_subject.subject.name", read_only=True)
    created_by_name = serializers.CharField(source="created_by.__str__", read_only=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.__str__", read_only=True)

    class Meta:
        model = SchemeOfWork
        fields = [
            "id",
            "academic_year",
            "academic_year_name",
            "term",
            "term_name",
            "curriculum_subject",
            "subject_name",
            "created_by",
            "created_by_name",
            "status",
            "submitted_at",
            "reviewed_by",
            "reviewed_by_name",
            "reviewed_at",
            "rejection_reason",
            "is_active",
            "items",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "status",
            "submitted_at",
            "reviewed_by",
            "reviewed_at",
            "rejection_reason",
            "created_at",
            "updated_at",
        ]


class LessonPlanMaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = LessonPlanMaterial
        fields = [
            "id",
            "lesson_plan",
            "title",
            "description",
            "file",
            "external_url",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def validate(self, attrs):
        from django.core.exceptions import ValidationError as DjangoValidationError
        from academic.services.lesson_material_service import LessonPlanMaterialService

        lesson_plan = attrs.get("lesson_plan") or getattr(self.instance, "lesson_plan", None)
        file = attrs.get("file", getattr(self.instance, "file", None))
        external_url = attrs.get(
            "external_url", getattr(self.instance, "external_url", "")
        )
        try:
            LessonPlanMaterialService.validate_material(
                lesson_plan=lesson_plan,
                file=file,
                external_url=external_url,
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return attrs


class LessonPlanSerializer(serializers.ModelSerializer):
    materials = LessonPlanMaterialSerializer(many=True, read_only=True)
    subject_name = serializers.CharField(source="allocation.subject.name", read_only=True)
    classroom_name = serializers.CharField(source="allocation.class_room.__str__", read_only=True)
    teacher_name = serializers.CharField(source="allocation.teacher_name.__str__", read_only=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.__str__", read_only=True)

    class Meta:
        model = LessonPlan
        fields = [
            "id",
            "scheme_item",
            "allocation",
            "subject_name",
            "classroom_name",
            "teacher_name",
            "lesson_date",
            "title",
            "duration_minutes",
            "learning_objectives",
            "subtopics",
            "previous_knowledge",
            "introduction",
            "lesson_content",
            "teacher_activities",
            "learner_activities",
            "teaching_materials",
            "evaluation",
            "assignment_notes",
            "references",
            "status",
            "rejection_reason",
            "submitted_at",
            "reviewed_at",
            "reviewed_by",
            "reviewed_by_name",
            "materials",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "status",
            "rejection_reason",
            "submitted_at",
            "reviewed_at",
            "reviewed_by",
            "created_at",
            "updated_at",
        ]


class LessonDeliverySerializer(serializers.ModelSerializer):
    lesson_plan_title = serializers.CharField(source="lesson_plan.__str__", read_only=True)
    recorded_by_name = serializers.CharField(source="recorded_by.__str__", read_only=True)

    class Meta:
        model = LessonDelivery
        fields = [
            "id",
            "lesson_plan",
            "lesson_plan_title",
            "status",
            "taught_at",
            "objectives_covered",
            "subtopics_covered",
            "teacher_notes",
            "learner_response",
            "follow_up_required",
            "follow_up_notes",
            "next_lesson_notes",
            "recorded_by",
            "recorded_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]
