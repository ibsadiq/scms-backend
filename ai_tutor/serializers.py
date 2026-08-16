from rest_framework import serializers
from .models import LessonTopic, LessonMaterial, TeacherAvatarSetting, TutorSession, TutorMessage
from academic.models import Teacher, Student, Subject, ClassRoom


class LessonMaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = LessonMaterial
        fields = ['id', 'lesson_topic', 'title', 'material_type', 'content_text', 'document_file', 'external_url', 'created_at']


class LessonTopicSerializer(serializers.ModelSerializer):
    materials = LessonMaterialSerializer(many=True, read_only=True)
    classroom_name = serializers.CharField(source='classroom.__str__', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    teacher_name = serializers.SerializerMethodField()

    class Meta:
        model = LessonTopic
        fields = [
            'id', 'classroom', 'classroom_name', 'subject', 'subject_name',
            'teacher', 'teacher_name', 'academic_year', 'term',
            'title', 'week_number', 'summary', 'learning_objectives',
            'is_published', 'materials', 'created_at', 'updated_at'
        ]

    def get_teacher_name(self, obj):
        if obj.teacher:
            return obj.teacher.full_name if hasattr(obj.teacher, 'full_name') else str(obj.teacher)
        return ''


class TeacherAvatarSettingSerializer(serializers.ModelSerializer):
    teacher_name = serializers.SerializerMethodField()
    teacher_image = serializers.SerializerMethodField()

    class Meta:
        model = TeacherAvatarSetting
        fields = [
            'id', 'teacher', 'teacher_name', 'teacher_image',
            'avatar_style', 'teaching_tone', 'custom_system_instructions',
            'is_ai_tutor_enabled', 'created_at', 'updated_at'
        ]

    def get_teacher_name(self, obj):
        return obj.teacher.full_name if hasattr(obj.teacher, 'full_name') else str(obj.teacher)

    def get_teacher_image(self, obj):
        if obj.teacher and obj.teacher.image:
            return obj.teacher.image.url
        return None


class TutorMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = TutorMessage
        fields = ['id', 'session', 'role', 'content', 'tokens_used', 'topic_referenced', 'created_at']


class TutorSessionSerializer(serializers.ModelSerializer):
    messages = TutorMessageSerializer(many=True, read_only=True)
    teacher_name = serializers.SerializerMethodField()
    teacher_image = serializers.SerializerMethodField()
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    lesson_topic_title = serializers.CharField(source='lesson_topic.title', read_only=True)

    class Meta:
        model = TutorSession
        fields = [
            'id', 'student', 'teacher', 'teacher_name', 'teacher_image',
            'subject', 'subject_name', 'lesson_topic', 'lesson_topic_title',
            'title', 'messages', 'created_at', 'updated_at'
        ]

    def get_teacher_name(self, obj):
        return obj.teacher.full_name if hasattr(obj.teacher, 'full_name') else str(obj.teacher)

    def get_teacher_image(self, obj):
        if obj.teacher and obj.teacher.image:
            return obj.teacher.image.url
        return None
