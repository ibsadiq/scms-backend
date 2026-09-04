from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from academic.models import (
    StudentsMedicalHistory,
    StudentsPreviousAcademicHistory,
    Student,
    Parent,
    ReasonLeft,
    ClassYear,
    ClassRoom,
)
from academic.serializers import ClassYearSerializer
from academic.services.student_creation_service import StudentCreationService
from academic.services.parent_identity_service import ParentIdentityService
from academic.services.parent_student_service import ParentStudentService


class BulkUploadFileSerializer(serializers.Serializer):
    file = serializers.FileField()
    send_invitations = serializers.BooleanField(required=False, default=True)


class BulkStudentUpdatedSerializer(serializers.Serializer):
    admission_number = serializers.CharField()
    full_name = serializers.CharField()
    reasons = serializers.ListField(child=serializers.CharField())


class BulkStudentSkippedSerializer(serializers.Serializer):
    admission_number = serializers.CharField()
    full_name = serializers.CharField()
    reason = serializers.CharField()


class BulkStudentUploadResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    updated_students = BulkStudentUpdatedSerializer(many=True)
    skipped_students = BulkStudentSkippedSerializer(many=True)
    not_created = serializers.ListField(child=serializers.JSONField())


class ReasonLeftSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReasonLeft
        fields = "__all__"


class StudentHealthRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentsMedicalHistory
        fields = "__all__"


class StudentsMedicalHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentsMedicalHistory
        fields = "__all__"


class StudentsPreviousAcademicHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentsPreviousAcademicHistory
        fields = "__all__"


class ParentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Parent
        fields = "__all__"


class SiblingSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    class_level = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            "id",
            "first_name",
            "middle_name",
            "last_name",
            "full_name",
            "admission_number",
            "gender",
            "class_level",
            "class_of_year",
        ]

    def get_full_name(self, obj):
        return obj.full_name

    def get_class_level(self, obj):
        return str(obj.classroom.grade_level) if obj.classroom and obj.classroom.grade_level else None


class StudentListSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    class_level_display = serializers.SerializerMethodField()
    classroom_display = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            "id",
            "first_name",
            "middle_name",
            "last_name",
            "full_name",
            "admission_number",
            "gender",
            "class_level_display",
            "classroom_display",
            "image",
            "status",
            "admission_date",
        ]
        read_only_fields = ["admission_number"]

    def get_full_name(self, obj):
        return obj.full_name

    def get_class_level_display(self, obj):
        return str(obj.classroom.grade_level) if obj.classroom and obj.classroom.grade_level else None

    def get_classroom_display(self, obj):
        if obj.classroom:
            return obj.classroom.name_display
        return None

    def get_status(self, obj):
        return obj.status


class StudentSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    class_level_display = serializers.SerializerMethodField()
    class_of_year_display = serializers.SerializerMethodField()
    parent_guardian_display = serializers.SerializerMethodField()
    classroom_display = serializers.SerializerMethodField()
    classroom_name = serializers.SerializerMethodField()
    grade_level = serializers.SerializerMethodField()
    grade_level_name = serializers.SerializerMethodField()
    siblings = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    portal_account_created = serializers.SerializerMethodField()
    image = serializers.ImageField(required=False, allow_null=True)
    class_level = serializers.CharField(write_only=True, required=False)
    classroom_id = serializers.PrimaryKeyRelatedField(
        queryset=ClassRoom.objects.all(), write_only=True, required=False
    )
    parent_email = serializers.EmailField(write_only=True, required=False, allow_blank=True)
    parent_first_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    parent_last_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    send_invitation = serializers.BooleanField(write_only=True, required=False, default=False)
    class_of_year = serializers.CharField(
        write_only=False, required=False, allow_null=True
    )

    class Meta:
        model = Student
        fields = [
            "id",
            "first_name",
            "middle_name",
            "last_name",
            "admission_number",
            "phone_number",
            "parent_contact",
            "region",
            "city",
            "street",
            "gender",
            "religion",
            "date_of_birth",
            "is_active",
            "full_name",
            "class_level_display",
            "class_of_year_display",
            "parent_guardian_display",
            "classroom_display",
            "classroom_name",
            "grade_level",
            "grade_level_name",
            "classroom",
            "classroom_id", # write-only
            "class_level",  # write-only
            "class_of_year",  # write-only
            "parent_email", # write-only
            "parent_first_name", # write-only
            "parent_last_name", # write-only
            "send_invitation", # write-only
            "siblings",
            "status",
            "image",
            "graduation_date",
            "date_dismissed",
            "reason_left",
            "admission_date",
            "can_login",
            "portal_account_created",
        ]
        read_only_fields = ["admission_number", "classroom", "can_login", "portal_account_created"]

    def get_status(self, obj):
        return obj.status

    def get_portal_account_created(self, obj):
        return bool(obj.user_id)

    def get_full_name(self, obj):
        return obj.full_name

    def get_class_level_display(self, obj):
        return str(obj.classroom.grade_level) if obj.classroom and obj.classroom.grade_level else None

    def get_class_of_year_display(self, obj):
        return obj.class_of_year.full_name if obj.class_of_year else None

    def get_parent_guardian_display(self, obj):
        if obj.parent_guardian:
            return f"{obj.parent_guardian.first_name} {obj.parent_guardian.last_name}".strip()
        return None

    def get_classroom_display(self, obj):
        if obj.classroom:
            return obj.classroom.name_display
        return None

    def get_classroom_name(self, obj):
        return str(obj.classroom) if obj.classroom else None

    def get_grade_level(self, obj):
        if obj.classroom and hasattr(obj.classroom, "grade_level") and obj.classroom.grade_level:
            return obj.classroom.grade_level.id
        return None

    def get_grade_level_name(self, obj):
        if obj.classroom and hasattr(obj.classroom, "grade_level") and obj.classroom.grade_level:
            gl = obj.classroom.grade_level
            return gl.alias if gl.alias else gl.default_name
        return None

    @extend_schema_field(SiblingSerializer(many=True))
    def get_siblings(self, obj):
        if not obj.parent_guardian_id:
            return []
        siblings = (
            Student.objects.filter(
                parent_guardian_id=obj.parent_guardian_id
            )
            .exclude(pk=obj.pk)
            .select_related("classroom", "classroom__grade_level")
        )
        return SiblingSerializer(siblings, many=True, context=self.context).data

    def validate_and_create_student(self, data):
        classroom = data.pop("classroom_id", None)
        if not classroom:
            raise serializers.ValidationError({"classroom_id": "Classroom is required for student creation."})

        class_level_name = data.pop("class_level", None)
        if class_level_name and classroom.grade_level:
            grade_names = [
                classroom.grade_level.system_code.lower(),
                (classroom.grade_level.default_name or "").lower(),
                (classroom.grade_level.alias or "").lower(),
                classroom.name.lower(),
            ]
            if class_level_name.lower() not in grade_names:
                raise serializers.ValidationError(
                    f"Mismatch: provided class_level '{class_level_name}' does not match classroom's grade '{classroom.grade_level}'."
                )

        class_of_year_name = data.pop("class_of_year", None)
        # ClassYear validation is kept for compatibility if passed
        if class_of_year_name:
            try:
                class_year = ClassYear.objects.get(year=class_of_year_name)
                data["class_of_year"] = class_year
            except ClassYear.DoesNotExist:
                raise serializers.ValidationError(f"Class year '{class_of_year_name}' does not exist.")

        # Normalize names
        data["first_name"] = data["first_name"].title()
        data["middle_name"] = data.get("middle_name", "").title()
        data["last_name"] = data["last_name"].title()

        send_invitation = data.pop("send_invitation", False)

        try:
            return StudentCreationService.create_student(
                classroom=classroom,
                first_name=data["first_name"],
                last_name=data["last_name"],
                parent_phone=data.get("parent_contact"),
                parent_email=data.pop("parent_email", None),
                student_phone=data.get("phone_number"),
                middle_name=data.get("middle_name", ""),
                gender=data.get("gender"),
                religion=data.get("religion"),
                date_of_birth=data.get("date_of_birth"),
                region=data.get("region", ""),
                city=data.get("city", ""),
                street=data.get("street", ""),
                admission_date=data.get("admission_date"),
                image=data.get("image"),
                parent_first_name=data.pop("parent_first_name", ""),
                parent_last_name=data.pop("parent_last_name", ""),
                parent_address=data.pop("parent_address", ""),
                actor=getattr(self.context.get("request"), "user", None),
                send_invitation=send_invitation,
            )
        except DjangoValidationError as e:
            detail = e.message_dict if hasattr(e, "message_dict") else e.messages
            raise serializers.ValidationError(detail)

    def create(self, validated_data):
        return self.validate_and_create_student(validated_data)

    def update(self, instance, validated_data):
        from django.db import transaction
        with transaction.atomic():
            validated_data.pop("class_level", None)
            classroom = validated_data.pop("classroom_id", None)
            if classroom:
                instance.classroom = classroom

            class_year_name = validated_data.pop("class_of_year", None)
            if class_year_name:
                try:
                    class_year = ClassYear.objects.get(year=class_year_name)
                    instance.class_of_year = class_year
                except ClassYear.DoesNotExist:
                    raise serializers.ValidationError(
                        f"Class year '{class_year_name}' does not exist."
                    )

            instance.first_name = validated_data.get(
                "first_name", instance.first_name
            ).title()
            instance.middle_name = validated_data.get(
                "middle_name", instance.middle_name
            ).title()
            instance.last_name = validated_data.get("last_name", instance.last_name).title()

            for field in [
                "parent_contact",
                "phone_number",
                "region",
                "city",
                "street",
                "gender",
                "religion",
                "date_of_birth",
                "image",
            ]:
                if field in validated_data:
                    setattr(instance, field, validated_data[field])

            # Update parent if needed
            contact = validated_data.get("parent_contact", instance.parent_contact)
            email = validated_data.get("parent_email", None)
            first_name = validated_data.get("parent_first_name", instance.middle_name or "Unknown")
            last_name = validated_data.get("parent_last_name", instance.last_name)

            parent_fields_supplied = any(
                field in validated_data
                for field in ("parent_contact", "parent_email", "parent_first_name", "parent_last_name")
            )
            if contact or email:
                parent = ParentIdentityService.resolve_parent(
                    phone_number=contact or instance.parent_contact,
                    email=email or (instance.parent_guardian.email if instance.parent_guardian else None),
                    first_name=first_name,
                    last_name=last_name,
                )
                instance.save()
                return ParentStudentService.assign_parent(instance, parent)
            if parent_fields_supplied and not contact and not email:
                instance.save()
                return ParentStudentService.assign_parent(instance, None)

            instance.save()
            return instance

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        parent = instance.parent_guardian
        ret["parent_email"] = parent.email if parent else None
        ret["parent_first_name"] = parent.first_name if parent else None
        ret["parent_last_name"] = parent.last_name if parent else None
        return ret

    def bulk_create(self, student_data_list):
        created_students = []
        errors = []

        for data in student_data_list:
            try:
                student = self.validate_and_create_student(data)
                created_students.append(student)
            except serializers.ValidationError as e:
                data["error"] = str(e)
                errors.append(data)

        return created_students, errors


class ScopedStudentReadSerializer(serializers.ModelSerializer):
    """Minimal student identity/class data for non-admin SIS readers."""

    full_name = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    classroom = serializers.StringRelatedField(read_only=True)
    class_level = serializers.SerializerMethodField()
    grade_level = serializers.SerializerMethodField()
    parent_email = serializers.CharField(read_only=True, default=None, allow_null=True)
    parent_first_name = serializers.CharField(read_only=True, default=None, allow_null=True)
    parent_last_name = serializers.CharField(read_only=True, default=None, allow_null=True)

    class Meta:
        model = Student
        fields = (
            "id",
            "first_name",
            "middle_name",
            "last_name",
            "full_name",
            "admission_number",
            "gender",
            "date_of_birth",
            "status",
            "classroom",
            "class_level",
            "grade_level",
            "image",
            "parent_email",
            "parent_first_name",
            "parent_last_name",
        )
        read_only_fields = fields

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        parent = instance.parent_guardian
        ret["parent_email"] = parent.email if parent else None
        ret["parent_first_name"] = parent.first_name if parent else None
        ret["parent_last_name"] = parent.last_name if parent else None
        return ret

    def get_class_level(self, obj):
        return str(obj.classroom.grade_level) if obj.classroom and obj.classroom.grade_level else None

    def get_grade_level(self, obj):
        grade_level = obj.classroom.grade_level if obj.classroom else None
        return str(grade_level) if grade_level else None


class TeacherStudentReadSerializer(ScopedStudentReadSerializer):
    """Educational identity only; excludes student demographic/profile details."""

    class Meta(ScopedStudentReadSerializer.Meta):
        fields = tuple(
            field
            for field in ScopedStudentReadSerializer.Meta.fields
            if field not in {"gender", "date_of_birth"}
        )
        read_only_fields = fields
