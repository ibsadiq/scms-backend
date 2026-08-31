from django.db import models
from django.core.exceptions import ValidationError

from academic.models import Teacher

from .attempt import (
    ExamAttempt,
    AttemptQuestion,
)

from .choices import (
    QuestionGradingStatus,
    GradingMethod,
    AttemptGradingStatus,
)


class AttemptQuestionGrade(models.Model):
    attempt_question = models.OneToOneField(
        AttemptQuestion,
        on_delete=models.CASCADE,
        related_name="grade",
    )

    awarded_marks = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
    )

    max_marks = models.DecimalField(
        max_digits=8,
        decimal_places=2,
    )

    is_correct = models.BooleanField(
        null=True,
        blank=True,
        help_text=(
            "True/False for objectively graded questions. "
            "May be null for manually graded questions."
        ),
    )

    status = models.CharField(
        max_length=30,
        choices=QuestionGradingStatus.choices,
    )

    grading_method = models.CharField(
        max_length=20,
        choices=GradingMethod.choices,
    )

    feedback = models.TextField(
        blank=True,
    )

    graded_by = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cbt_question_grades",
    )

    graded_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        indexes = [
            models.Index(
                fields=[
                    "status",
                    "grading_method",
                ]
            ),
        ]

    def clean(self):
        errors = {}

        if self.awarded_marks < 0:
            errors["awarded_marks"] = (
                "Awarded marks cannot be negative."
            )

        if self.max_marks <= 0:
            errors["max_marks"] = (
                "Maximum marks must be greater than zero."
            )

        if (
            self.awarded_marks is not None
            and self.max_marks is not None
            and self.awarded_marks > self.max_marks
        ):
            errors["awarded_marks"] = (
                "Awarded marks cannot exceed maximum marks."
            )

        if errors:
            raise ValidationError(errors)

        super().clean()

    def __str__(self):
        return (
            f"{self.attempt_question} - "
            f"{self.awarded_marks}/{self.max_marks}"
        )


class AttemptGrade(models.Model):
    attempt = models.OneToOneField(
        ExamAttempt,
        on_delete=models.CASCADE,
        related_name="grade",
    )

    status = models.CharField(
        max_length=30,
        choices=AttemptGradingStatus.choices,
        default=AttemptGradingStatus.PENDING,
    )

    raw_score = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    total_marks = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    percentage = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
    )

    normalized_score = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=(
            "Final CBT score normalized to the "
            "AssessmentComponent max_score."
        ),
    )

    graded_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    posted_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    grading_error = models.TextField(
        blank=True,
        help_text="Internal grading failure detail; never exposed to students.",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return (
            f"{self.attempt} - "
            f"{self.raw_score}/{self.total_marks}"
        )
