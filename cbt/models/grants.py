import uuid

from django.core.exceptions import ValidationError
from django.db import models

from academic.models import Student, Teacher

from .choices import AttemptGrantSource, AttemptGrantStatus
from .exam import CBTExam
from .publication import PublishedExamRevision


class AttemptGrant(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    nonce = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    student = models.ForeignKey(
        Student, on_delete=models.PROTECT, related_name="cbt_attempt_grants"
    )
    exam = models.ForeignKey(
        CBTExam, on_delete=models.PROTECT, related_name="attempt_grants"
    )
    published_revision = models.ForeignKey(
        PublishedExamRevision,
        on_delete=models.PROTECT,
        related_name="attempt_grants",
    )
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    status = models.CharField(
        max_length=12,
        choices=AttemptGrantStatus.choices,
        default=AttemptGrantStatus.ACTIVE,
    )
    issuance_source = models.CharField(
        max_length=24,
        choices=AttemptGrantSource.choices,
        default=AttemptGrantSource.ONLINE_START,
    )
    issued_by = models.ForeignKey(
        Teacher,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="issued_cbt_attempt_grants",
    )
    issued_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        Teacher,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="revoked_cbt_attempt_grants",
    )
    revocation_reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-issued_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(valid_from__lt=models.F("valid_until")),
                name="attempt_grant_valid_interval",
            ),
            models.UniqueConstraint(
                fields=["student", "exam", "published_revision"],
                condition=models.Q(status=AttemptGrantStatus.ACTIVE),
                name="unique_active_attempt_grant",
            ),
        ]
        indexes = [
            models.Index(fields=["student", "exam", "status"]),
            models.Index(fields=["published_revision", "status"]),
            models.Index(fields=["valid_until"]),
        ]

    def clean(self):
        errors = {}
        if self.valid_from and self.valid_until and self.valid_from >= self.valid_until:
            errors["valid_until"] = "Grant validity end must be after its start."
        if self.published_revision_id and self.exam_id:
            if self.published_revision.exam_id != self.exam_id:
                errors["published_revision"] = "Grant revision must belong to its exam."
        if errors:
            raise ValidationError(errors)
        super().clean()

    def save(self, *args, **kwargs):
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).values(
                "public_id", "nonce", "student_id", "exam_id", "published_revision_id"
            ).first()
            if original and any(
                original[field] != getattr(self, field)
                for field in (
                    "public_id", "nonce", "student_id", "exam_id", "published_revision_id"
                )
            ):
                raise ValidationError("Attempt grant identity and binding are immutable.")
        return super().save(*args, **kwargs)

    @property
    def is_revoked(self):
        return self.status == AttemptGrantStatus.REVOKED
