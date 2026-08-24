from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from academic.models import (
    ClassYear,
    ClassRoom,
    GradeLevel,
    ClassLevel,
    Department,
    ReasonLeft,
    Stream,
    SchoolSection,
)


class ClassYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassYear
        fields = "__all__"


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = "__all__"


class ClassLevelSerializer(serializers.ModelSerializer):
    grade_level_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ClassLevel
        fields = ["id", "name", "grade_level", "grade_level_name"]
        read_only_fields = ["id", "grade_level_name"]

    def get_grade_level_name(self, obj):
        if obj.grade_level:
            return obj.grade_level.alias or obj.grade_level.default_name
        return None


class StreamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stream
        fields = "__all__"


class SchoolSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchoolSection
        fields = ["id", "system_code", "default_name", "alias", "sequence_order"]


class GradeLevelSerializer(serializers.ModelSerializer):
    section_display = serializers.CharField(source="get_section_display", read_only=True)

    class Meta:
        model = GradeLevel
        fields = [
            "id",
            "system_code",
            "default_name",
            "alias",
            "section",
            "section_display",
            "sequence_order",
            "min_age",
            "max_age",
            "updated_at",
        ]
        read_only_fields = ["id", "updated_at"]


class ClassRoomSerializer(serializers.ModelSerializer):
    name_display = serializers.SerializerMethodField(read_only=True)
    class_teacher_name = serializers.SerializerMethodField()
    stream_name = serializers.SerializerMethodField()
    stream_id = serializers.IntegerField(source="stream.id", read_only=True, allow_null=True)
    available_sits = serializers.IntegerField(read_only=True)
    class_status = serializers.CharField(read_only=True)

    class Meta:
        model = ClassRoom
        fields = [
            "id",
            "name",
            "name_display",
            "stream",
            "stream_name",
            "stream_id",
            "class_teacher",
            "class_teacher_name",
            "capacity",
            "occupied_sits",
            "available_sits",
            "class_status",
        ]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        readable = str(instance)
        representation["name_display"] = readable
        representation["display_name"] = readable
        return representation

    @extend_schema_field(serializers.CharField)
    def get_name_display(self, obj):
        return obj.name.name if obj.name else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_stream_name(self, obj):
        if obj.stream:
            return obj.stream.name
        return None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_class_teacher_name(self, obj):
        if obj.class_teacher:
            return f"{obj.class_teacher.first_name} {obj.class_teacher.last_name}"
        return None


class SchoolYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassYear
        fields = "__all__"


class ReasonLeftSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReasonLeft
        fields = "__all__"


class BulkUploadClassRoomsSerializer(serializers.Serializer):
    file = serializers.FileField()


class BulkUploadSubjectsSerializer(serializers.Serializer):
    file = serializers.FileField()
