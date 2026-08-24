import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from academic.models import Staff, Student


def empty_layout():
    return {"schema_version": 1, "elements": []}


def empty_layout_v2():
    return {
        "schema_version": 2,
        "coordinate_system": {"unit": "design_unit", "width": 10000, "height": 6306},
        "background": {"type": "color", "color": "#ffffff"},
        "safe_area": {"top": 250, "right": 250, "bottom": 250, "left": 250},
        "elements": [],
    }


class HolderType(models.TextChoices):
    STUDENT = "STUDENT", "Student"
    STAFF = "STAFF", "Staff"


class IDCardTemplate(models.Model):
    """Stable tenant-local identity for a reusable ID-card design."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=120)
    holder_type = models.CharField(max_length=10, choices=HolderType.choices, db_index=True)
    description = models.TextField(blank=True)
    is_archived = models.BooleanField(default=False, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name="created_idcard_templates", null=True, blank=True,
    )
    current_draft_version = models.ForeignKey(
        "IDCardTemplateVersion", on_delete=models.SET_NULL,
        related_name="draft_for_templates", null=True, blank=True,
    )
    current_published_version = models.ForeignKey(
        "IDCardTemplateVersion", on_delete=models.SET_NULL,
        related_name="published_for_templates", null=True, blank=True,
    )
    # ID1 compatibility mirrors. Version rows are authoritative for new writes;
    # these fields keep the existing frontend/API contract operational.
    width_mm = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("85.60"))
    height_mm = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("53.98"))
    front_layout = models.JSONField(default=empty_layout)
    back_layout = models.JSONField(default=empty_layout)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")
        constraints = [
            models.UniqueConstraint(fields=("name", "holder_type"), name="unique_idcard_template_name_holder"),
            models.CheckConstraint(condition=Q(width_mm__gt=0), name="idcard_template_width_positive"),
            models.CheckConstraint(condition=Q(height_mm__gt=0), name="idcard_template_height_positive"),
        ]
        indexes = [models.Index(fields=("holder_type", "is_active"))]

    def clean(self):
        from idcards.services.layout import LayoutValidator

        errors = {}
        orientation = "LANDSCAPE" if self.width_mm >= self.height_mm else "PORTRAIT"
        for field in ("front_layout", "back_layout"):
            try:
                LayoutValidator.validate(
                    getattr(self, field), self.holder_type, width_mm=self.width_mm,
                    height_mm=self.height_mm, orientation=orientation,
                )
            except ValidationError as exc:
                errors[field] = exc.messages
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.name} ({self.get_holder_type_display()})"


class IDCardTemplateVersion(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"
        ARCHIVED = "ARCHIVED", "Archived"

    class Orientation(models.TextChoices):
        LANDSCAPE = "LANDSCAPE", "Landscape"
        PORTRAIT = "PORTRAIT", "Portrait"

    template = models.ForeignKey(IDCardTemplate, on_delete=models.PROTECT, related_name="versions")
    version_number = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    width_mm = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("85.60"))
    height_mm = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("53.98"))
    orientation = models.CharField(max_length=10, choices=Orientation.choices, default=Orientation.LANDSCAPE)
    front_layout = models.JSONField(default=empty_layout_v2)
    back_layout = models.JSONField(default=empty_layout_v2)
    created_from_version = models.ForeignKey(
        "self", on_delete=models.PROTECT, related_name="derived_versions", null=True, blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name="created_idcard_template_versions", null=True, blank=True,
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name="published_idcard_template_versions", null=True, blank=True,
    )
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("template_id", "-version_number")
        constraints = [
            models.UniqueConstraint(fields=("template", "version_number"), name="unique_idcard_template_version"),
            models.UniqueConstraint(
                fields=("template",), condition=Q(status="DRAFT"),
                name="one_draft_idcard_template_version",
            ),
            models.CheckConstraint(condition=Q(width_mm__gt=0), name="idcard_version_width_positive"),
            models.CheckConstraint(condition=Q(height_mm__gt=0), name="idcard_version_height_positive"),
        ]

    def clean(self):
        from idcards.services.layout import LayoutValidator

        errors = {}
        if self.template_id:
            for field in ("front_layout", "back_layout"):
                try:
                    LayoutValidator.validate(
                        getattr(self, field), self.template.holder_type,
                        width_mm=self.width_mm, height_mm=self.height_mm,
                        orientation=self.orientation,
                    )
                except ValidationError as exc:
                    errors[field] = exc.messages
        if self.orientation == self.Orientation.LANDSCAPE and self.width_mm < self.height_mm:
            errors["orientation"] = "Landscape versions require width to be at least height."
        if self.orientation == self.Orientation.PORTRAIT and self.height_mm < self.width_mm:
            errors["orientation"] = "Portrait versions require height to be at least width."
        if self.created_from_version_id and self.created_from_version.template_id != self.template_id:
            errors["created_from_version"] = "The source version must belong to the same template."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).values(
                "status", "width_mm", "height_mm", "orientation", "front_layout", "back_layout", "template_id"
            ).first()
            if original and original["status"] == self.Status.PUBLISHED:
                immutable = ("width_mm", "height_mm", "orientation", "front_layout", "back_layout", "template_id")
                if any(original[field] != getattr(self, field) for field in immutable):
                    raise ValidationError("Published template versions are immutable.")
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.template.name} v{self.version_number} ({self.get_status_display()})"


class IDCard(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"
        REVOKED = "REVOKED", "Revoked"
        REPLACED = "REPLACED", "Replaced"

    student = models.ForeignKey(
        Student, on_delete=models.PROTECT, related_name="id_cards", null=True, blank=True
    )
    staff = models.ForeignKey(
        Staff, on_delete=models.PROTECT, related_name="id_cards", null=True, blank=True
    )
    template = models.ForeignKey(IDCardTemplate, on_delete=models.PROTECT, related_name="issued_cards")
    template_version = models.ForeignKey(
        IDCardTemplateVersion, on_delete=models.PROTECT,
        related_name="issued_cards",
    )
    card_number = models.CharField(max_length=30, unique=True, db_index=True, editable=False)
    verification_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    issued_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    deactivation_reason = models.CharField(max_length=255, blank=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="issued_id_cards", null=True, blank=True
    )
    replaces = models.OneToOneField(
        "self", on_delete=models.PROTECT, related_name="replacement_card",
        null=True, blank=True,
    )
    replacement_reason = models.CharField(max_length=255, blank=True)
    replaced_at = models.DateTimeField(null=True, blank=True)
    replaced_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name="replacement_id_cards", null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-issued_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=(Q(student__isnull=False, staff__isnull=True) | Q(student__isnull=True, staff__isnull=False)),
                name="idcard_exactly_one_holder",
            ),
            models.UniqueConstraint(
                fields=("student",), condition=Q(status="ACTIVE"),
                name="one_active_idcard_per_student",
            ),
            models.UniqueConstraint(
                fields=("staff",), condition=Q(status="ACTIVE"),
                name="one_active_idcard_per_staff",
            ),
        ]
        indexes = [
            models.Index(fields=("student", "status")),
            models.Index(fields=("staff", "status")),
            models.Index(fields=("template", "status")),
        ]

    @property
    def holder_type(self):
        return HolderType.STUDENT if self.student_id else HolderType.STAFF

    @property
    def effective_status(self):
        if self.status == self.Status.ACTIVE and self.expires_at and self.expires_at <= timezone.now():
            return "EXPIRED"
        return self.status

    def clean(self):
        if bool(self.student_id) == bool(self.staff_id):
            raise ValidationError("An ID card must belong to exactly one student or staff member.")
        if self.template_id and self.template.holder_type != self.holder_type:
            raise ValidationError({"template": "Template holder type does not match the card holder."})
        if self.template_version_id and self.template_version.template_id != self.template_id:
            raise ValidationError({"template_version": "Template version does not belong to the selected template."})

    def __str__(self):
        return self.card_number


class RFIDCredential(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        REVOKED = "REVOKED", "Revoked"
        LOST = "LOST", "Lost"
        REPLACED = "REPLACED", "Replaced"

    id_card = models.ForeignKey(IDCard, on_delete=models.PROTECT, related_name="rfid_credentials")
    uid_hash = models.CharField(max_length=64, unique=True, editable=False)
    uid_last_four = models.CharField(max_length=4, editable=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    assigned_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="revoked_rfid_credentials",
        null=True, blank=True,
    )
    revocation_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-assigned_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("id_card",), condition=Q(status="ACTIVE"), name="one_active_rfid_per_idcard"
            )
        ]
        indexes = [models.Index(fields=("id_card", "status"))]

    @property
    def masked_uid(self):
        return f"********{self.uid_last_four}"

    def __str__(self):
        return f"{self.id_card.card_number} – {self.masked_uid}"
