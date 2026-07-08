from rest_framework import serializers
from .models import AllocatedSubject, Teacher, Subject, ClassRoom, AcademicYear, Term


class AllocatedSubjectSerializer(serializers.ModelSerializer):
    """Serializer for AllocatedSubject model"""
    teacher_name = serializers.PrimaryKeyRelatedField(
        queryset=Teacher.objects.all(),
        write_only=True
    )
    teacher_display = serializers.CharField(
        source='teacher_name',
        read_only=True
    )
    subject = serializers.PrimaryKeyRelatedField(
        queryset=Subject.objects.all()
    )
    subject_name = serializers.CharField(
        source='subject.name',
        read_only=True
    )
    academic_year = serializers.PrimaryKeyRelatedField(
        queryset=AcademicYear.objects.all()
    )
    academic_year_display = serializers.CharField(
        source='academic_year.year',
        read_only=True
    )
    term = serializers.PrimaryKeyRelatedField(
        queryset=Term.objects.all(),
        required=False,
        allow_null=True
    )
    term_name = serializers.CharField(
        source='term.name',
        read_only=True
    )
    class_room = serializers.PrimaryKeyRelatedField(
        queryset=ClassRoom.objects.all()
    )
    class_room_display = serializers.CharField(
        source='class_room',
        read_only=True
    )

    class Meta:
        model = AllocatedSubject
        fields = [
            'id',
            'teacher_name',
            'teacher_display',
            'subject',
            'subject_name',
            'academic_year',
            'academic_year_display',
            'term',
            'term_name',
            'class_room',
            'class_room_display',
            'weekly_periods',
            'max_daily_periods',
        ]
        read_only_fields = ['id']

    def to_representation(self, instance):
        """Custom representation to include teacher info"""
        data = super().to_representation(instance)
        if instance.teacher_name and instance.teacher_name.user:
            data['teacher_display'] = f"{instance.teacher_name.user.first_name} {instance.teacher_name.user.last_name}".strip()
        return data


class AllocatedSubjectListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views"""
    id = serializers.IntegerField(read_only=True)
    teacher_name = serializers.SerializerMethodField()
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    class_room_display = serializers.CharField(source='class_room', read_only=True)
    academic_year_display = serializers.CharField(source='academic_year.year', read_only=True)
    term_name = serializers.CharField(source='term.name', read_only=True, allow_null=True)

    class Meta:
        model = AllocatedSubject
        fields = [
            'id',
            'teacher_name',
            'subject_name',
            'class_room_display',
            'academic_year_display',
            'term_name',
            'weekly_periods',
        ]

    def get_teacher_name(self, obj):
        if obj.teacher_name and obj.teacher_name.user:
            return f"{obj.teacher_name.user.first_name} {obj.teacher_name.user.last_name}".strip()
        return str(obj.teacher_name)
