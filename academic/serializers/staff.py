from rest_framework import serializers
from academic.models import (
    Subject,
    Department,
    AllocatedSubject,
    Teacher,
    ClassRoom,
    AcademicYear,
    Term,
    MessageToTeacher,
    Staff,
)


class SubjectSerializer(serializers.ModelSerializer):
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), allow_null=True, required=False
    )
    department_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Subject
        fields = [
            "id",
            "name",
            "subject_code",
            "description",
            "department",
            "department_name",
            "graded",
            "is_selectable",
        ]

    def get_department_name(self, obj):
        return obj.department.name.title() if obj.department else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["name"] = instance.name.title() if instance.name else instance.name
        return data

    def validate_subject_code(self, value):
        if value and len(value) < 3:
            raise serializers.ValidationError(
                "Subject code must be at least 3 characters."
            )
        return value


class AllocatedSubjectSerializer(serializers.ModelSerializer):
    """Serializer for AllocatedSubject model"""
    teacher_name = serializers.PrimaryKeyRelatedField(
        queryset=Teacher.objects.all(),
        required=True,
    )
    teacher_display = serializers.SerializerMethodField()
    teacher_name_display = serializers.SerializerMethodField()

    subject = serializers.PrimaryKeyRelatedField(
        queryset=Subject.objects.all()
    )
    subject_name = serializers.CharField(
        source="subject.name",
        read_only=True,
    )

    academic_year = serializers.PrimaryKeyRelatedField(
        queryset=AcademicYear.objects.all()
    )
    academic_year_display = serializers.CharField(
        source="academic_year.name",
        read_only=True,
    )
    academic_year_name = serializers.CharField(
        source="academic_year.name",
        read_only=True,
    )

    term = serializers.PrimaryKeyRelatedField(
        queryset=Term.objects.all(),
        required=False,
        allow_null=True,
    )
    term_name = serializers.CharField(
        source="term.name",
        read_only=True,
        allow_null=True,
    )

    class_room = serializers.PrimaryKeyRelatedField(
        queryset=ClassRoom.objects.all()
    )
    class_room_display = serializers.SerializerMethodField()
    class_room_name = serializers.SerializerMethodField()

    class Meta:
        model = AllocatedSubject
        fields = [
            "id",
            "teacher_name",
            "teacher_display",
            "teacher_name_display",
            "subject",
            "subject_name",
            "academic_year",
            "academic_year_display",
            "academic_year_name",
            "term",
            "term_name",
            "class_room",
            "class_room_display",
            "class_room_name",
            "weekly_periods",
            "max_daily_periods",
            "is_mandatory",
        ]
        read_only_fields = ["id"]

    def get_teacher_display(self, obj):
        if obj.teacher_name:
            if obj.teacher_name.user:
                fname = obj.teacher_name.user.first_name or ""
                lname = obj.teacher_name.user.last_name or ""
                name = f"{fname} {lname}".strip()
                if name:
                    return name
                return obj.teacher_name.user.email or f"Teacher #{obj.teacher_name.id}"
            return str(obj.teacher_name)
        return "Unassigned"

    def get_teacher_name_display(self, obj):
        return self.get_teacher_display(obj)

    def get_class_room_display(self, obj):
        if obj.class_room:
            cr = obj.class_room
            if hasattr(cr, "name_display") and cr.name_display:
                return str(cr.name_display)
            if cr.name:
                cname = cr.name.name if hasattr(cr.name, "name") else str(cr.name)
                if hasattr(cr, "stream") and cr.stream and hasattr(cr.stream, "name"):
                    return f"{cname} {cr.stream.name}"
                return cname
            return str(cr)
        return "N/A"

    def get_class_room_name(self, obj):
        return self.get_class_room_display(obj)


class AllocatedSubjectListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views"""
    id = serializers.IntegerField(read_only=True)
    teacher_name = serializers.SerializerMethodField()
    teacher_display = serializers.SerializerMethodField()
    teacher_name_display = serializers.SerializerMethodField()
    teacher_id = serializers.SerializerMethodField()

    subject_id = serializers.IntegerField(source="subject.id", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)

    class_room_id = serializers.IntegerField(source="class_room.id", read_only=True)
    class_room_display = serializers.SerializerMethodField()
    class_room_name = serializers.SerializerMethodField()

    academic_year_id = serializers.IntegerField(source="academic_year.id", read_only=True)
    academic_year_display = serializers.CharField(source="academic_year.name", read_only=True)
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)

    term_id = serializers.IntegerField(source="term.id", read_only=True, allow_null=True)
    term_name = serializers.CharField(source="term.name", read_only=True, allow_null=True)

    class Meta:
        model = AllocatedSubject
        fields = [
            "id",
            "teacher_name",
            "teacher_display",
            "teacher_name_display",
            "teacher_id",
            "subject",
            "subject_id",
            "subject_name",
            "class_room",
            "class_room_id",
            "class_room_display",
            "class_room_name",
            "academic_year",
            "academic_year_id",
            "academic_year_display",
            "academic_year_name",
            "term",
            "term_id",
            "term_name",
            "weekly_periods",
            "max_daily_periods",
            "is_mandatory",
        ]

    def get_teacher_id(self, obj):
        return obj.teacher_name.id if obj.teacher_name else None

    def get_teacher_name(self, obj):
        if obj.teacher_name:
            if obj.teacher_name.user:
                fname = obj.teacher_name.user.first_name or ""
                lname = obj.teacher_name.user.last_name or ""
                name = f"{fname} {lname}".strip()
                if name:
                    return name
                return obj.teacher_name.user.email or f"Teacher #{obj.teacher_name.id}"
            return str(obj.teacher_name)
        return "Unassigned"

    def get_teacher_display(self, obj):
        return self.get_teacher_name(obj)

    def get_teacher_name_display(self, obj):
        return self.get_teacher_name(obj)

    def get_class_room_display(self, obj):
        if obj.class_room:
            cr = obj.class_room
            if hasattr(cr, "name_display") and cr.name_display:
                return str(cr.name_display)
            if cr.name:
                cname = cr.name.name if hasattr(cr.name, "name") else str(cr.name)
                if hasattr(cr, "stream") and cr.stream and hasattr(cr.stream, "name"):
                    return f"{cname} {cr.stream.name}"
                return cname
            return str(cr)
        return "N/A"

    def get_class_room_name(self, obj):
        return self.get_class_room_display(obj)


class MessageToTeacherSerializer(serializers.ModelSerializer):
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = MessageToTeacher
        fields = ["id", "message", "start_date", "end_date", "is_active"]


class StaffSerializer(serializers.ModelSerializer):
    """
    Canonical serializer for Staff identities in school management workflows.
    Minimizes exposure of sensitive user/HR data while providing all necessary
    fields for holder selection and identification.
    """
    full_name = serializers.CharField(read_only=True)
    first_name = serializers.SerializerMethodField(read_only=True)
    last_name = serializers.SerializerMethodField(read_only=True)
    department_name = serializers.SerializerMethodField(read_only=True)
    role_display = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = Staff
        fields = [
            "id",
            "staff_id",
            "full_name",
            "first_name",
            "last_name",
            "role",
            "role_display",
            "designation",
            "department",
            "department_name",
            "image",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_first_name(self, obj):
        if obj.user and obj.user.first_name:
            return obj.user.first_name
        return ""

    def get_last_name(self, obj):
        if obj.user and obj.user.last_name:
            return obj.user.last_name
        return ""

    def get_department_name(self, obj):
        if obj.department and obj.department.name:
            return obj.department.name.title()
        return None


