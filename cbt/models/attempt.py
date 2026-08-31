import uuid

from django.db import models
from django.core.exceptions import ValidationError

from academic.models import Student, StudentClassEnrollment

from .choices import ExamAttemptStatus
from .exam import CBTExam, ExamQuestion
from .answer_definitions import QuestionOption, MatchingPair


class ExamAttempt(models.Model):
    cbt_exam = models.ForeignKey(
        CBTExam,
        on_delete=models.PROTECT,
        related_name="attempts",
    )

    student = models.ForeignKey(
        Student,
        on_delete=models.PROTECT,
        related_name="cbt_attempts",
    )

    enrollment = models.ForeignKey(
        StudentClassEnrollment,
        on_delete=models.PROTECT,
        related_name="cbt_attempts",
    )

    status = models.CharField(
        max_length=20,
        choices=ExamAttemptStatus.choices,
        default=ExamAttemptStatus.IN_PROGRESS,
    )

    started_at = models.DateTimeField()

    expires_at = models.DateTimeField()

    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    last_activity_at = models.DateTimeField(
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
        ordering = ["-started_at"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "cbt_exam",
                    "student",
                ],
                name="unique_student_attempt_per_cbt_exam",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "cbt_exam",
                    "student",
                ]
            ),
            models.Index(
                fields=[
                    "cbt_exam",
                    "status",
                ]
            ),
            models.Index(
                fields=[
                    "student",
                    "status",
                ]
            ),
        ]

    def __str__(self):
        return (
            f"{self.student} - "
            f"{self.cbt_exam} - "
            f"{self.get_status_display()}"
        )

    def clean(self):
        errors = {}

        if self.enrollment_id and self.student_id:
            if self.enrollment.student_id != self.student_id:
                errors["enrollment"] = (
                    "Enrollment must belong to the "
                    "selected student."
                )

        if self.enrollment_id and self.cbt_exam_id:
            if (
                self.enrollment.classroom_id
                != self.cbt_exam.classroom_id
            ):
                errors["enrollment"] = (
                    "Enrollment classroom must match "
                    "the CBT exam classroom."
                )

            if (
                self.enrollment.academic_year_id
                != self.cbt_exam.session.academic_year_id
            ):
                errors["enrollment"] = (
                    "Enrollment academic year must match "
                    "the CBT exam academic year."
                )

        if (
            self.started_at
            and self.expires_at
            and self.expires_at <= self.started_at
        ):
            errors["expires_at"] = (
                "Attempt expiry must be after its start time."
            )

        if errors:
            raise ValidationError(errors)

        super().clean()

class AttemptQuestion(models.Model):
    attempt = models.ForeignKey(
        ExamAttempt,
        on_delete=models.CASCADE,
        related_name="attempt_questions",
    )

    exam_question = models.ForeignKey(
        ExamQuestion,
        on_delete=models.PROTECT,
        related_name="attempt_questions",
    )

    display_order = models.PositiveIntegerField()

    is_flagged = models.BooleanField(
        default=False,
        help_text="Student marked this question for review.",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["display_order"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "attempt",
                    "exam_question",
                ],
                name="unique_exam_question_per_attempt",
            ),
            models.UniqueConstraint(
                fields=[
                    "attempt",
                    "display_order",
                ],
                name="unique_attempt_question_display_order",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "attempt",
                    "display_order",
                ]
            ),
        ]

    def clean(self):
        errors = {}

        if (
            self.attempt_id
            and self.exam_question_id
            and self.exam_question.cbt_exam_id
            != self.attempt.cbt_exam_id
        ):
            errors["exam_question"] = (
                "Exam question must belong to the "
                "same CBT exam as the attempt."
            )

        if (
            self.display_order is not None
            and self.display_order <= 0
        ):
            errors["display_order"] = (
                "Display order must be greater than zero."
            )

        if errors:
            raise ValidationError(errors)

        super().clean()

    def __str__(self):
        return (
            f"{self.attempt} - "
            f"Question {self.display_order}"
        )

class AttemptQuestionOption(models.Model):
    attempt_question = models.ForeignKey(
        AttemptQuestion,
        on_delete=models.CASCADE,
        related_name="option_order",
    )

    question_option = models.ForeignKey(
        QuestionOption,
        on_delete=models.PROTECT,
        related_name="attempt_presentations",
    )

    display_order = models.PositiveIntegerField()

    class Meta:
        ordering = ["display_order"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "attempt_question",
                    "question_option",
                ],
                name="unique_option_per_attempt_question",
            ),
            models.UniqueConstraint(
                fields=[
                    "attempt_question",
                    "display_order",
                ],
                name="unique_attempt_option_display_order",
            ),
        ]


class AttemptMatchingItem(models.Model):
    class Side(models.TextChoices):
        LEFT = "LEFT", "Left"
        RIGHT = "RIGHT", "Right"

    attempt_question = models.ForeignKey(
        AttemptQuestion,
        on_delete=models.CASCADE,
        related_name="matching_item_order",
    )
    matching_pair = models.ForeignKey(
        MatchingPair,
        on_delete=models.PROTECT,
        related_name="attempt_presentations",
    )
    side = models.CharField(max_length=5, choices=Side.choices)
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    display_order = models.PositiveIntegerField()

    class Meta:
        ordering = ["side", "display_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["attempt_question", "matching_pair", "side"],
                name="unique_matching_item_side_per_attempt_question",
            ),
            models.UniqueConstraint(
                fields=["attempt_question", "side", "display_order"],
                name="unique_matching_item_order_per_side",
            ),
        ]
