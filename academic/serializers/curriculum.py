from rest_framework import serializers
from academic.models import (
    Curriculum,
    CurriculumSubject,
    Topic,
    CurriculumTopic,
    CurriculumGuidance,
    SubTopic,
    LearningObjective,
)


class SubTopicSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubTopic
        fields = ["id", "topic", "name", "is_active", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]


class TopicSerializer(serializers.ModelSerializer):
    subtopics = SubTopicSerializer(many=True, read_only=True)
    grade_level_name = serializers.CharField(source="grade_level.__str__", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)

    class Meta:
        model = Topic
        fields = [
            "id",
            "name",
            "grade_level",
            "grade_level_name",
            "subject",
            "subject_name",
            "subtopics",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class LearningObjectiveSerializer(serializers.ModelSerializer):
    class Meta:
        model = LearningObjective
        fields = [
            "id",
            "curriculum_topic",
            "subtopic",
            "description",
            "order",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class CurriculumGuidanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = CurriculumGuidance
        fields = [
            "id",
            "curriculum_topic",
            "teacher_activities",
            "learner_activities",
            "teaching_learning_materials",
            "evaluation_guide",
            "notes",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]


class CurriculumTopicSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source="topic.name", read_only=True)
    guidance = CurriculumGuidanceSerializer(read_only=True)
    learning_objectives = LearningObjectiveSerializer(many=True, read_only=True)

    class Meta:
        model = CurriculumTopic
        fields = [
            "id",
            "curriculum_subject",
            "topic",
            "topic_name",
            "theme",
            "content_summary",
            "order",
            "is_active",
            "guidance",
            "learning_objectives",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class CurriculumSubjectSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    grade_level_name = serializers.CharField(source="grade_level.__str__", read_only=True)

    class Meta:
        model = CurriculumSubject
        fields = [
            "id",
            "curriculum",
            "subject",
            "subject_name",
            "grade_level",
            "grade_level_name",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class CurriculumSerializer(serializers.ModelSerializer):
    subjects = CurriculumSubjectSerializer(many=True, read_only=True)

    class Meta:
        model = Curriculum
        fields = [
            "id",
            "name",
            "authority_type",
            "authority_name",
            "version",
            "description",
            "effective_from",
            "effective_to",
            "is_active",
            "subjects",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]
