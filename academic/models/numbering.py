import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


NUMBER_PATTERN_TOKENS = {
    "{PREFIX}",
    "{YYYY}",
    "{YY}",
    "{SECTION}",
    "{SEQ}",
}

NUMBER_PATTERN_TOKEN_RE = re.compile(
    r"\{[^{}]+\}"
)

NUMBER_PATTERN_STATIC_RE = re.compile(
    r"[A-Za-z0-9/_\-. ]*"
)

NUMBER_PREFIX_RE = re.compile(
    r"[A-Za-z0-9._/-]+"
)


class NumberResetPolicy(models.TextChoices):
    NEVER = "never", "Never"
    ACADEMIC_YEAR = "academic_year", "Academic year"


class NumberSequenceType(models.TextChoices):
    STUDENT_ADMISSION = (
        "student_admission",
        "Student admission number",
    )

    ADMISSION_APPLICATION = (
        "admission_application",
        "Admission application number",
    )


def validate_number_pattern(value):
    if not value:
        raise ValidationError(
            "Pattern is required."
        )

    tokens = NUMBER_PATTERN_TOKEN_RE.findall(value)

    if tokens.count("{SEQ}") != 1:
        raise ValidationError(
            "Pattern must contain {SEQ} exactly once."
        )

    unsupported_tokens = sorted({
        token
        for token in tokens
        if token not in NUMBER_PATTERN_TOKENS
    })

    if unsupported_tokens:
        raise ValidationError(
            "Pattern contains unsupported token(s): "
            + ", ".join(unsupported_tokens)
        )

    remainder = NUMBER_PATTERN_TOKEN_RE.sub(
        "",
        value,
    )

    if "{" in remainder or "}" in remainder:
        raise ValidationError(
            "Pattern contains malformed braces."
        )

    if not NUMBER_PATTERN_STATIC_RE.fullmatch(
        remainder
    ):
        raise ValidationError(
            "Pattern contains unsupported characters."
        )


class BaseNumberPolicy(models.Model):
    pattern = models.CharField(
        max_length=100,
        validators=[validate_number_pattern],
    )

    prefix = models.CharField(
        max_length=30,
    )

    sequence_width = models.PositiveSmallIntegerField(
        default=4,
    )

    reset_policy = models.CharField(
        max_length=20,
        choices=NumberResetPolicy.choices,
        default=NumberResetPolicy.ACADEMIC_YEAR,
    )

    is_active = models.BooleanField(
        default=True,
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        abstract = True

    @property
    def uses_section(self):
        return "{SECTION}" in self.pattern

    @property
    def uses_full_year(self):
        return "{YYYY}" in self.pattern

    @property
    def uses_short_year(self):
        return "{YY}" in self.pattern

    def clean(self):
        super().clean()

        validate_number_pattern(self.pattern)

        if not 1 <= self.sequence_width <= 12:
            raise ValidationError({
                "sequence_width": (
                    "Width must be between 1 and 12."
                )
            })

        if not self.prefix:
            raise ValidationError({
                "prefix": "Prefix is required."
            })

        if "{" in self.prefix or "}" in self.prefix:
            raise ValidationError({
                "prefix": (
                    "Prefix cannot contain template braces."
                )
            })

        if not NUMBER_PREFIX_RE.fullmatch(
            self.prefix
        ):
            raise ValidationError({
                "prefix": (
                    "Prefix contains unsupported characters."
                )
            })


class StudentAdmissionNumberPolicy(
    BaseNumberPolicy
):
    pattern = models.CharField(
        max_length=100,
        default="{PREFIX}/{YYYY}/{SEQ}",
        validators=[validate_number_pattern],
    )

    prefix = models.CharField(
        max_length=30,
        default="ADM",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["is_active"],
                condition=Q(is_active=True),
                name=(
                    "academic_one_active_"
                    "student_number_policy"
                ),
            ),
        ]


class AdmissionApplicationNumberPolicy(
    BaseNumberPolicy
):
    pattern = models.CharField(
        max_length=100,
        default="{PREFIX}/{YYYY}/{SEQ}",
        validators=[validate_number_pattern],
    )

    prefix = models.CharField(
        max_length=30,
        default="APP",
    )

    sequence_width = models.PositiveSmallIntegerField(
        default=3,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["is_active"],
                condition=Q(is_active=True),
                name=(
                    "academic_one_active_"
                    "application_number_policy"
                ),
            ),
        ]


class NumberSequence(models.Model):
    sequence_type = models.CharField(
        max_length=30,
        choices=NumberSequenceType.choices,
    )

    reset_policy = models.CharField(
        max_length=20,
        choices=NumberResetPolicy.choices,
    )

    scope_key = models.CharField(
        max_length=100,
    )

    last_value = models.PositiveBigIntegerField(
        default=0,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "sequence_type",
                    "reset_policy",
                    "scope_key",
                ],
                name=(
                    "academic_unique_"
                    "number_sequence_scope"
                ),
            ),
        ]

    def __str__(self):
        return (
            f"{self.sequence_type}: "
            f"{self.scope_key} = "
            f"{self.last_value}"
        )