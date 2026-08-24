import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class NumberResetPolicy(models.TextChoices):
    NEVER = "never", "Never"
    ACADEMIC_YEAR = "academic_year", "Academic year"


def validate_number_pattern(value):
    tokens = re.findall(r"\{[^{}]+\}", value or "")
    allowed = {"{PREFIX}", "{YEAR}", "{YEAR2}", "{SEQ}"}
    if not value or tokens.count("{SEQ}") != 1:
        raise ValidationError("Pattern must contain {SEQ} exactly once.")
    if any(token not in allowed for token in tokens):
        raise ValidationError("Pattern contains an unsupported token.")
    remainder = re.sub(r"\{[^{}]+\}", "", value)
    if "{" in remainder or "}" in remainder:
        raise ValidationError("Pattern contains malformed braces.")
    if not re.fullmatch(r"[A-Za-z0-9/_\-. ]*", remainder):
        raise ValidationError("Pattern contains unsupported characters.")


class BaseNumberPolicy(models.Model):
    pattern = models.CharField(max_length=100, validators=[validate_number_pattern])
    prefix = models.CharField(max_length=30)
    sequence_width = models.PositiveSmallIntegerField(default=4)
    reset_policy = models.CharField(
        max_length=20, choices=NumberResetPolicy.choices,
        default=NumberResetPolicy.ACADEMIC_YEAR,
    )
    is_active = models.BooleanField(default=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        validate_number_pattern(self.pattern)
        if not 1 <= self.sequence_width <= 12:
            raise ValidationError({"sequence_width": "Width must be between 1 and 12."})
        if "{" in self.prefix or "}" in self.prefix:
            raise ValidationError({"prefix": "Prefix cannot contain template braces."})
        if not re.fullmatch(r"[A-Za-z0-9._/-]+", self.prefix or ""):
            raise ValidationError({"prefix": "Prefix contains unsupported characters."})


class StudentAdmissionNumberPolicy(BaseNumberPolicy):
    pattern = models.CharField(
        max_length=100, default="{PREFIX}-{YEAR}-{SEQ}",
        validators=[validate_number_pattern],
    )
    prefix = models.CharField(max_length=30, default="ADM")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["is_active"], condition=Q(is_active=True),
                name="academic_one_active_student_number_policy",
            )
        ]


class AdmissionApplicationNumberPolicy(BaseNumberPolicy):
    pattern = models.CharField(
        max_length=100, default="{PREFIX}/{YEAR}/{SEQ}",
        validators=[validate_number_pattern],
    )
    prefix = models.CharField(max_length=30, default="ADM")
    sequence_width = models.PositiveSmallIntegerField(default=3)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["is_active"], condition=Q(is_active=True),
                name="academic_one_active_application_number_policy",
            )
        ]


class AdmissionApplicationNumberSequence(models.Model):
    reset_policy = models.CharField(max_length=20, choices=NumberResetPolicy.choices)
    scope_key = models.CharField(max_length=40)
    last_value = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["reset_policy", "scope_key"],
                name="academic_unique_application_number_scope",
            )
        ]
