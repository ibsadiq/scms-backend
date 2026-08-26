import copy

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from idcards.models import (
    AuthorizedSignature, AuthorizedSignatureVersion, IDCard, IDCardDesignAsset,
    IDCardTemplate, IDCardTemplateAssignment, IDCardTemplateVersion, RFIDCredential,
)
from idcards.services import (
    AuthorizedSignatureService, CardService, IDCardAssetService,
    IDCardTemplateLifecycleService, RFIDCredentialService,
)


class AuthorizedSignatureVersionSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = AuthorizedSignatureVersion
        fields = (
            "id", "public_id", "signature", "version_number", "image", "image_url",
            "mime_type", "width", "height", "file_size", "content_hash",
            "uploaded_by", "created_at",
        )
        read_only_fields = (
            "public_id", "signature", "version_number", "mime_type", "width",
            "height", "file_size", "content_hash", "uploaded_by", "created_at",
        )

    def get_image_url(self, obj):
        return obj.image.url if obj.image else ""


class AuthorizedSignatureSerializer(serializers.ModelSerializer):
    current_version = AuthorizedSignatureVersionSerializer(read_only=True)
    versions_count = serializers.SerializerMethodField()

    class Meta:
        model = AuthorizedSignature
        fields = (
            "id", "public_id", "name", "signatory_name", "signatory_title",
            "description", "is_active", "current_version", "current_version_id",
            "versions_count", "created_by", "created_at", "updated_at",
        )
        read_only_fields = (
            "public_id", "current_version", "current_version_id", "versions_count",
            "created_by", "created_at", "updated_at",
        )

    def get_versions_count(self, obj):
        return obj.versions.count()


class AuthorizedSignatureCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    signatory_name = serializers.CharField(max_length=120)
    signatory_title = serializers.CharField(max_length=120)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    image = serializers.ImageField()


class AuthorizedSignatureReplaceSerializer(serializers.Serializer):
    image = serializers.ImageField()


class IDCardTemplateFieldSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    group = serializers.CharField()
    type = serializers.ChoiceField(choices=("text", "image", "date"))
    example_value = serializers.CharField(allow_blank=True)
    max_expected_length = serializers.IntegerField()
    sensitivity = serializers.CharField()


class IDCardDesignAssetSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = IDCardDesignAsset
        fields = (
            "id", "public_id", "name", "asset_type", "file", "file_url",
            "mime_type", "width", "height", "file_size", "content_hash",
            "is_active", "uploaded_by", "created_at", "updated_at",
        )
        read_only_fields = (
            "public_id", "mime_type", "width", "height", "file_size",
            "content_hash", "uploaded_by", "created_at", "updated_at",
        )

    def get_file_url(self, obj):
        return obj.file.url if obj.file else ""


class IDCardDesignAssetUploadSerializer(serializers.Serializer):
    file = serializers.ImageField()
    name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    asset_type = serializers.ChoiceField(
        choices=IDCardDesignAsset.AssetType.choices,
        default=IDCardDesignAsset.AssetType.IMAGE,
    )


class TemplateDuplicateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)


class IDCardTemplateVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = IDCardTemplateVersion
        fields = (
            "id", "template", "version_number", "status", "width_mm", "height_mm",
            "orientation", "front_layout", "back_layout", "created_from_version",
            "created_by", "published_by", "published_at", "created_at", "updated_at",
        )
        read_only_fields = (
            "template", "version_number", "status", "created_from_version", "created_by",
            "published_by", "published_at", "created_at", "updated_at",
        )

    def update(self, instance, validated_data):
        try:
            return IDCardTemplateLifecycleService.update_draft(instance, **validated_data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)


class IDCardTemplateSerializer(serializers.ModelSerializer):
    current_draft = IDCardTemplateVersionSerializer(source="current_draft_version", read_only=True)
    current_published = IDCardTemplateVersionSerializer(source="current_published_version", read_only=True)
    assignment_count = serializers.IntegerField(source="assignments.count", read_only=True)

    class Meta:
        model = IDCardTemplate
        fields = (
            "id", "public_id", "name", "holder_type", "description", "is_archived",
            "is_active", "width_mm", "height_mm", "front_layout", "back_layout",
            "current_draft_version", "current_published_version", "current_draft",
            "current_published", "created_by", "created_at", "updated_at",
            "assignment_count",
        )
        read_only_fields = (
            "public_id", "is_archived", "current_draft_version", "current_published_version",
            "current_draft", "current_published", "created_by", "created_at", "updated_at",
        )
        validators = []

    def validate(self, attrs):
        instance = copy.copy(self.instance) if self.instance else IDCardTemplate()
        for key, value in attrs.items():
            setattr(instance, key, value)
        try:
            instance.full_clean(exclude=("id",), validate_unique=False, validate_constraints=False)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
        return attrs

    def create(self, validated_data):
        validated_data.pop("is_active", None)
        try:
            return IDCardTemplateLifecycleService.create_template(
                actor=self.context["request"].user, **validated_data,
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)

    def update(self, instance, validated_data):
        validated_data.pop("is_active", None)
        if "holder_type" in validated_data and validated_data["holder_type"] != instance.holder_type:
            raise serializers.ValidationError({"holder_type": "Holder type cannot change after creation."})
        instance.name = validated_data.pop("name", instance.name)
        instance.description = validated_data.pop("description", instance.description)
        instance.save(update_fields=("name", "description", "updated_at"))
        version_fields = {key: validated_data[key] for key in (
            "width_mm", "height_mm", "front_layout", "back_layout"
        ) if key in validated_data}
        if version_fields:
            draft = instance.current_draft_version
            if not draft:
                draft = IDCardTemplateLifecycleService.create_draft(instance, actor=self.context["request"].user)
            if "width_mm" in version_fields or "height_mm" in version_fields:
                width = version_fields.get("width_mm", draft.width_mm)
                height = version_fields.get("height_mm", draft.height_mm)
                version_fields["orientation"] = "LANDSCAPE" if width >= height else "PORTRAIT"
            IDCardTemplateLifecycleService.update_draft(draft, **version_fields)
        instance.refresh_from_db()
        return instance


class IDCardTemplateAssignmentSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source="template.name", read_only=True)
    published_version = serializers.IntegerField(source="template.current_published_version.version_number", read_only=True)
    target_label = serializers.SerializerMethodField()

    class Meta:
        model = IDCardTemplateAssignment
        fields = ("id", "public_id", "holder_type", "scope_type", "template", "template_name",
                  "published_version", "section", "grade_level", "classroom", "department",
                  "staff_role", "target_label", "is_active", "created_by", "created_at", "updated_at")
        read_only_fields = ("public_id", "template_name", "published_version", "target_label", "created_by", "created_at", "updated_at")

    def get_target_label(self, obj):
        target = obj.section or obj.grade_level or obj.classroom or obj.department
        return str(target) if target else (obj.get_staff_role_display() if obj.staff_role else "All holders")

    def validate(self, attrs):
        instance = copy.copy(self.instance) if self.instance else IDCardTemplateAssignment()
        for key, value in attrs.items():
            setattr(instance, key, value)
        try:
            instance.full_clean(exclude=("id",), validate_unique=True, validate_constraints=True)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
        return attrs

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


class IDCardSerializer(serializers.ModelSerializer):
    holder_type = serializers.CharField(read_only=True)
    effective_status = serializers.CharField(read_only=True)
    holder_name = serializers.SerializerMethodField()
    holder_identifier = serializers.SerializerMethodField()
    holder_context = serializers.SerializerMethodField()
    template_name = serializers.CharField(source="template.name", read_only=True)
    active_rfid = serializers.SerializerMethodField()

    class Meta:
        model = IDCard
        fields = (
            "id", "student", "staff", "holder_type", "template", "card_number",
            "template_version",
            "verification_token", "issued_at", "expires_at", "status", "effective_status",
            "deactivated_at", "deactivation_reason", "issued_by", "created_at", "updated_at",
            "replaces", "replacement_reason", "replaced_at", "replaced_by",
            "holder_name", "holder_identifier", "holder_context", "template_name",
            "active_rfid",
        )
        read_only_fields = (
            "card_number", "verification_token", "issued_at", "status", "template_version", "deactivated_at",
            "deactivation_reason", "issued_by", "created_at", "updated_at",
            "replaces", "replacement_reason", "replaced_at", "replaced_by",
        )
        extra_kwargs = {"template": {"required": False}}

    def get_holder_name(self, obj):
        return obj.student.full_name if obj.student_id else obj.staff.full_name

    def get_holder_identifier(self, obj):
        return obj.student.admission_number if obj.student_id else obj.staff.staff_id

    def get_holder_context(self, obj):
        if obj.student_id:
            return str(obj.student.classroom) if obj.student.classroom_id else ""
        return obj.staff.designation or obj.staff.get_role_display()

    def get_active_rfid(self, obj):
        credential = next(
            (item for item in obj.rfid_credentials.all() if item.status == RFIDCredential.Status.ACTIVE),
            None,
        )
        if not credential:
            return None
        return {"id": credential.id, "masked_uid": credential.masked_uid, "status": credential.status}

    def validate(self, attrs):
        if bool(attrs.get("student")) == bool(attrs.get("staff")):
            raise serializers.ValidationError("Provide exactly one student or staff member.")
        return attrs

    def create(self, validated_data):
        actor = self.context["request"].user
        if validated_data.get("student"):
            return CardService.issue_student_card(issued_by=actor, **validated_data)
        return CardService.issue_staff_card(issued_by=actor, **validated_data)


class CardDeactivateSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)
    revoke = serializers.BooleanField(default=False)


class CardReplaceSerializer(serializers.Serializer):
    template = serializers.PrimaryKeyRelatedField(queryset=IDCardTemplate.objects.filter(is_active=True), required=False)
    template_version = serializers.PrimaryKeyRelatedField(queryset=IDCardTemplateVersion.objects.all(), required=False)
    reason = serializers.CharField(required=False, default="Replacement", max_length=255)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, attrs):
        template = attrs.get("template")
        version = attrs.get("template_version")
        if template and version and version.template_id != template.pk:
            raise serializers.ValidationError({"template_version": "Version does not belong to the selected template."})
        return attrs


class RFIDCredentialSerializer(serializers.ModelSerializer):
    uid = serializers.CharField(write_only=True, required=False)
    masked_uid = serializers.CharField(read_only=True)

    class Meta:
        model = RFIDCredential
        fields = ("id", "id_card", "uid", "masked_uid", "status", "assigned_at", "revoked_at", "revoked_by", "revocation_reason", "created_at", "updated_at")
        read_only_fields = ("status", "assigned_at", "revoked_at", "revoked_by", "revocation_reason", "created_at", "updated_at")

    def validate(self, attrs):
        if not self.instance and not attrs.get("uid"):
            raise serializers.ValidationError({"uid": "This field is required."})
        return attrs

    def create(self, validated_data):
        return RFIDCredentialService.assign(id_card=validated_data["id_card"], uid=validated_data["uid"])


class RFIDRevokeSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)
    status = serializers.ChoiceField(choices=(RFIDCredential.Status.REVOKED, RFIDCredential.Status.LOST), default=RFIDCredential.Status.REVOKED)


class RFIDReplaceSerializer(serializers.Serializer):
    uid = serializers.CharField()
    reason = serializers.CharField(required=False, default="Replacement", max_length=255)
