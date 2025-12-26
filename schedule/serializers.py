from rest_framework import serializers
from .models import Period
from academic.models import AllocatedSubject, Subject, ClassRoom, Teacher
from academic.serializers import ClassRoomSerializer


class PeriodListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing periods with nested data for display.
    """
    teacher_name = serializers.SerializerMethodField()
    subject_name = serializers.SerializerMethodField()
    classroom_name = serializers.SerializerMethodField()

    class Meta:
        model = Period
        fields = [
            "id",
            "day_of_week",
            "start_time",
            "end_time",
            "teacher",
            "teacher_name",
            "subject",
            "subject_name",
            "classroom",
            "classroom_name",
            "room_number",
            "is_active",
            "notes",
        ]
        read_only_fields = ["id"]

    def get_teacher_name(self, obj):
        if obj.teacher:
            return f"{obj.teacher.first_name} {obj.teacher.last_name}"
        return None

    def get_subject_name(self, obj):
        if obj.subject and obj.subject.subject:
            return obj.subject.subject.name
        return None

    def get_classroom_name(self, obj):
        if obj.classroom:
            return obj.classroom.class_name
        return None


class PeriodCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating periods.
    Handles conflict validation.
    """
    class Meta:
        model = Period
        fields = [
            "id",
            "day_of_week",
            "start_time",
            "end_time",
            "classroom",
            "subject",
            "teacher",
            "room_number",
            "is_active",
            "notes",
        ]
        read_only_fields = ["id"]

    def validate(self, data):
        """
        Custom validation to check for conflicts.
        This runs in addition to model's clean() method.
        """
        start_time = data.get('start_time')
        end_time = data.get('end_time')

        # Validate time order
        if start_time and end_time:
            if end_time <= start_time:
                raise serializers.ValidationError({
                    'end_time': 'End time must be after start time.'
                })

        return data

    def create(self, validated_data):
        """
        Create a new period.
        The model's clean() method will handle conflict detection.
        """
        try:
            period = Period(**validated_data)
            period.full_clean()  # This will call the model's clean() method
            period.save()
            return period
        except Exception as e:
            raise serializers.ValidationError(str(e))

    def update(self, instance, validated_data):
        """
        Update an existing period.
        The model's clean() method will handle conflict detection.
        """
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        try:
            instance.full_clean()  # This will call the model's clean() method
            instance.save()
            return instance
        except Exception as e:
            raise serializers.ValidationError(str(e))


class PeriodSerializer(serializers.ModelSerializer):
    """
    Backward compatible serializer (existing code uses this).
    """
    teacher_name = serializers.SerializerMethodField()
    subject_name = serializers.SerializerMethodField()
    classroom_name = serializers.SerializerMethodField()

    class Meta:
        model = Period
        fields = [
            "id",
            "day_of_week",
            "start_time",
            "end_time",
            "teacher",
            "teacher_name",
            "subject",
            "subject_name",
            "classroom",
            "classroom_name",
            "room_number",
            "is_active",
        ]
        read_only_fields = ["id"]

    def get_teacher_name(self, obj):
        if obj.teacher:
            return f"{obj.teacher.first_name} {obj.teacher.last_name}"
        return None

    def get_subject_name(self, obj):
        if obj.subject and obj.subject.subject:
            return obj.subject.subject.name
        return None

    def get_classroom_name(self, obj):
        if obj.classroom:
            return obj.classroom.class_name
        return None
