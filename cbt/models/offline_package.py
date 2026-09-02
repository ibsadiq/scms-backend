import uuid

from django.core.exceptions import ValidationError
from django.db import models

from academic.models import Student

from .exam import CBTExam
from .grants import AttemptGrant
from .publication import PublishedExamRevision


class OfflineExamPackage(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    student = models.ForeignKey(
        Student, on_delete=models.PROTECT, related_name="cbt_offline_packages"
    )
    exam = models.ForeignKey(
        CBTExam, on_delete=models.PROTECT, related_name="offline_packages"
    )
    published_revision = models.ForeignKey(
        PublishedExamRevision,
        on_delete=models.PROTECT,
        related_name="offline_packages",
    )
    attempt_grant = models.OneToOneField(
        AttemptGrant,
        on_delete=models.PROTECT,
        related_name="offline_package",
    )
    schema_version = models.PositiveIntegerField(default=1)
    presentation_seed = models.UUIDField(default=uuid.uuid4, editable=False)
    package_hash = models.CharField(max_length=64, blank=True)
    package_signature = models.TextField(blank=True)
    content = models.JSONField(default=dict)
    generated_at = models.DateTimeField(auto_now_add=True)
    first_downloaded_at = models.DateTimeField(null=True, blank=True)
    last_downloaded_at = models.DateTimeField(null=True, blank=True)
    download_count = models.PositiveBigIntegerField(default=0)

    class Meta:
        ordering = ["-generated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "attempt_grant", "published_revision"],
                name="unique_offline_package_binding",
            ),
        ]
        indexes = [
            models.Index(fields=["student", "exam"]),
            models.Index(fields=["published_revision"]),
        ]

    def clean(self):
        errors = {}
        if self.attempt_grant_id:
            grant = self.attempt_grant
            if grant.student_id != self.student_id:
                errors["student"] = "Package student must match its grant."
            if grant.exam_id != self.exam_id:
                errors["exam"] = "Package exam must match its grant."
            if grant.published_revision_id != self.published_revision_id:
                errors["published_revision"] = "Package revision must match its grant."
        if errors:
            raise ValidationError(errors)
        super().clean()

    def save(self, *args, **kwargs):
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).values(
                "public_id", "student_id", "exam_id", "published_revision_id",
                "attempt_grant_id", "schema_version", "presentation_seed",
                "package_hash", "package_signature",
                "content",
            ).first()
            immutable = (
                "public_id", "student_id", "exam_id", "published_revision_id",
                "attempt_grant_id", "schema_version", "presentation_seed",
                "package_hash", "package_signature",
                "content",
            )
            if original and any(
                original[field] != getattr(self, field) for field in immutable
            ):
                raise ValidationError("Offline package identity and content are immutable.")
        return super().save(*args, **kwargs)
