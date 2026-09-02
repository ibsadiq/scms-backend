import uuid

from django.db import models
from django.core.exceptions import ValidationError

from academic.models import Student, StudentClassEnrollment

from .choices import AttemptStartSource, ExamAttemptStatus
from .exam import CBTExam, ExamQuestion
from .answer_definitions import QuestionOption, MatchingPair
from .publication import (
    PublishedExamRevision,
    PublishedExamQuestion,
    PublishedExamChoice,
    PublishedExamMatchingItem,
)
from .grants import AttemptGrant
from .offline_package import OfflineExamPackage


class ExamAttempt(models.Model):
    public_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

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

    published_revision = models.ForeignKey(
        PublishedExamRevision,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="attempts",
    )

    attempt_grant = models.OneToOneField(
        AttemptGrant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="attempt",
    )

    offline_package = models.OneToOneField(
        OfflineExamPackage,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="attempt",
    )

    start_source = models.CharField(
        max_length=24,
        choices=AttemptStartSource.choices,
        default=AttemptStartSource.ONLINE,
    )

    client_reported_started_at = models.DateTimeField(null=True, blank=True)
    server_reconciled_at = models.DateTimeField(null=True, blank=True)
    client_reported_submitted_at = models.DateTimeField(null=True, blank=True)

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

    revision = models.PositiveBigIntegerField(default=0)

    submission_id = models.UUIDField(
        null=True,
        blank=True,
        unique=True,
        editable=False,
    )

    submitted_revision = models.PositiveBigIntegerField(null=True, blank=True)

    submission_snapshot_hash = models.CharField(max_length=64, blank=True)

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

    def save(self, *args, **kwargs):
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).values(
                "public_id", "attempt_grant_id", "published_revision_id",
                "offline_package_id", "start_source",
                "client_reported_started_at", "server_reconciled_at",
            ).first()
            if original and self.public_id != original["public_id"]:
                raise ValidationError("Attempt public identity cannot be changed.")
            if original and original["attempt_grant_id"] != self.attempt_grant_id:
                raise ValidationError("Attempt grant binding cannot be changed.")
            if original and original["published_revision_id"] != self.published_revision_id:
                raise ValidationError("Attempt published revision cannot be changed.")
            for field in (
                "offline_package_id", "start_source",
                "client_reported_started_at", "server_reconciled_at",
            ):
                if original and original[field] != getattr(self, field):
                    raise ValidationError("Attempt offline-start provenance cannot be changed.")
        return super().save(*args, **kwargs)

    def clean(self):
        errors = {}

        if self.published_revision_id:
            if self.published_revision.exam_id != self.cbt_exam_id:
                errors["published_revision"] = "Published revision must belong to this exam."
            elif self.published_revision.status != PublishedExamRevision.Status.FINALIZED:
                errors["published_revision"] = "Attempts require a finalized revision."

        if self.attempt_grant_id:
            if self.attempt_grant.student_id != self.student_id:
                errors["attempt_grant"] = "Attempt grant must belong to the student."
            elif self.attempt_grant.exam_id != self.cbt_exam_id:
                errors["attempt_grant"] = "Attempt grant must belong to the exam."
            elif self.attempt_grant.published_revision_id != self.published_revision_id:
                errors["attempt_grant"] = "Attempt and grant revisions must match."

        if self.offline_package_id:
            package = self.offline_package
            if package.student_id != self.student_id:
                errors["offline_package"] = "Attempt and package students must match."
            elif package.exam_id != self.cbt_exam_id:
                errors["offline_package"] = "Attempt and package exams must match."
            elif package.published_revision_id != self.published_revision_id:
                errors["offline_package"] = "Attempt and package revisions must match."
            elif package.attempt_grant_id != self.attempt_grant_id:
                errors["offline_package"] = "Attempt and package grants must match."

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
    public_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    attempt = models.ForeignKey(
        ExamAttempt,
        on_delete=models.CASCADE,
        related_name="attempt_questions",
    )

    exam_question = models.ForeignKey(
        ExamQuestion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="attempt_questions",
    )

    published_question = models.ForeignKey(
        PublishedExamQuestion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
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
            models.CheckConstraint(
                condition=(
                    models.Q(exam_question__isnull=False, published_question__isnull=True)
                    | models.Q(exam_question__isnull=True, published_question__isnull=False)
                ),
                name="attempt_question_has_one_source",
            ),
            models.UniqueConstraint(
                fields=["attempt", "published_question"],
                name="unique_published_question_per_attempt",
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

        if self.published_question_id:
            if not self.attempt.published_revision_id:
                errors["published_question"] = "Published question requires a revision-backed attempt."
            elif self.published_question.revision_id != self.attempt.published_revision_id:
                errors["published_question"] = "Published question must belong to the attempt revision."

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

    def save(self, *args, **kwargs):
        if self.pk:
            original_public_id = type(self).objects.filter(pk=self.pk).values_list(
                "public_id", flat=True
            ).first()
            if original_public_id and self.public_id != original_public_id:
                raise ValidationError("Attempt-question public identity cannot be changed.")
        return super().save(*args, **kwargs)

class AttemptQuestionOption(models.Model):
    attempt_question = models.ForeignKey(
        AttemptQuestion,
        on_delete=models.CASCADE,
        related_name="option_order",
    )

    question_option = models.ForeignKey(
        QuestionOption,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="attempt_presentations",
    )

    published_choice = models.ForeignKey(
        PublishedExamChoice,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
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
            models.UniqueConstraint(
                fields=["attempt_question", "published_choice"],
                name="unique_published_option_per_attempt_question",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(question_option__isnull=False, published_choice__isnull=True)
                    | models.Q(question_option__isnull=True, published_choice__isnull=False)
                ),
                name="attempt_option_has_one_source",
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
        null=True,
        blank=True,
        related_name="attempt_presentations",
    )
    published_item = models.ForeignKey(
        PublishedExamMatchingItem,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
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
            models.UniqueConstraint(
                fields=["attempt_question", "published_item", "side"],
                name="unique_published_matching_item_side",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(matching_pair__isnull=False, published_item__isnull=True)
                    | models.Q(matching_pair__isnull=True, published_item__isnull=False)
                ),
                name="attempt_matching_item_has_one_source",
            ),
        ]
