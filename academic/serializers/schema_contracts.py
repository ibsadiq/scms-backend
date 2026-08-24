from rest_framework import serializers


class TeacherHomeroomClassSerializer(serializers.Serializer):
    id = serializers.CharField()
    classroom_id = serializers.IntegerField()
    classroom_name = serializers.CharField()
    grade_level_name = serializers.CharField()
    student_count = serializers.IntegerField()


class TeacherAssignmentSerializer(TeacherHomeroomClassSerializer):
    id = serializers.IntegerField()
    subject_id = serializers.IntegerField(allow_null=True)
    subject_name = serializers.CharField()
    is_class_teacher = serializers.BooleanField()
    schedule = serializers.ListField(child=serializers.JSONField())


class TeacherClassesResponseSerializer(serializers.Serializer):
    homeroom_classes = TeacherHomeroomClassSerializer(many=True)
    teaching_assignments = TeacherAssignmentSerializer(many=True)


class ClassroomStudentResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    admission_number = serializers.CharField(allow_null=True)
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.EmailField(allow_blank=True)
    phone = serializers.CharField(allow_blank=True)
    photo = serializers.CharField(allow_null=True)
    status = serializers.ChoiceField(choices=("active",))
    grade_level_name = serializers.CharField()
    classroom_name = serializers.CharField()
    score = serializers.FloatField(allow_null=True)
    remarks = serializers.CharField(allow_blank=True)


class TeacherScheduleEntrySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    day_of_week = serializers.CharField()
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    subject_name = serializers.CharField()
    classroom_name = serializers.CharField()
    grade_level_name = serializers.CharField()
    room_number = serializers.CharField()
    is_active = serializers.BooleanField()
