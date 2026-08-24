from rest_framework import serializers
from .models import TeacherAvatarSetting, TutorSession, TutorMessage, TutorSessionInsight
from academic.models import Teacher, Student, Subject, LessonPlan, LessonDelivery, CurriculumTopic, LearningObjective


class TeacherAvatarSettingSerializer(serializers.ModelSerializer):
    teacher_name = serializers.SerializerMethodField()
    teacher_image = serializers.SerializerMethodField()

    class Meta:
        model = TeacherAvatarSetting
        fields = [
            "id",
            "teacher",
            "teacher_name",
            "teacher_image",
            "avatar_style",
            "teaching_tone",
            "custom_system_instructions",
            "is_ai_tutor_enabled",
            "allow_direct_answers",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_teacher_name(self, obj):
        return getattr(obj.teacher, "full_name", str(obj.teacher))

    def get_teacher_image(self, obj):
        if obj.teacher and getattr(obj.teacher, "image", None):
            return obj.teacher.image.url
        return None


class TutorMessageSerializer(serializers.ModelSerializer):
    learning_objective_description = serializers.CharField(
        source="learning_objective.description",
        read_only=True,
    )

    class Meta:
        model = TutorMessage
        fields = [
            "id",
            "session",
            "role",
            "content",
            "tokens_used",
            "learning_objective",
            "learning_objective_description",
            "created_at",
        ]
        read_only_fields = ["id", "tokens_used", "created_at"]


class TutorSessionInsightSerializer(serializers.ModelSerializer):
    class Meta:
        model = TutorSessionInsight
        fields = [
            "id",
            "session",
            "summary",
            "misconceptions",
            "concepts_struggled_with",
            "concepts_mastered",
            "follow_up_recommended",
            "teacher_attention_required",
            "updated_at",
        ]
        read_only_fields = ["id", "updated_at"]


class TutorSessionSerializer(serializers.ModelSerializer):
    messages = TutorMessageSerializer(many=True, read_only=True)
    insight = TutorSessionInsightSerializer(read_only=True)
    student_name = serializers.SerializerMethodField()
    teacher_name = serializers.SerializerMethodField()
    teacher_image = serializers.SerializerMethodField()
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    lesson_plan_title = serializers.CharField(source="lesson_plan.title", read_only=True)
    curriculum_topic_name = serializers.CharField(
        source="curriculum_topic.topic.name",
        read_only=True,
    )

    class Meta:
        model = TutorSession
        fields = [
            "id",
            "student",
            "student_name",
            "teacher",
            "teacher_name",
            "teacher_image",
            "subject",
            "subject_name",
            "lesson_plan",
            "lesson_plan_title",
            "lesson_delivery",
            "curriculum_topic",
            "curriculum_topic_name",
            "learning_objectives",
            "title",
            "insight",
            "messages",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "teacher", "created_at", "updated_at"]

    def get_student_name(self, obj):
        return getattr(obj.student, "full_name", f"{obj.student.first_name} {obj.student.last_name}").strip()

    def get_teacher_name(self, obj):
        return getattr(obj.teacher, "full_name", str(obj.teacher))

    def get_teacher_image(self, obj):
        if obj.teacher and getattr(obj.teacher, "image", None):
            return obj.teacher.image.url
        return None
