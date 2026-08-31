from django.db import models
from django.core.exceptions import ValidationError

from academic.models import (
    Subject,
    GradeLevel,
    Topic,
    SubTopic,
    Teacher,
    LearningObjective,
)

from .choices import (
    QuestionType,
    QuestionDifficulty,
    QuestionStatus,
)
from .immutability import ensure_question_version_mutable, VersionContentImmutabilityMixin


class QuestionBank(models.Model):
    name = models.CharField(max_length=150)

    description = models.TextField(blank=True)

    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="question_banks",
    )

    grade_levels = models.ManyToManyField(
        GradeLevel,
        related_name="question_banks",
        blank=True,
    )

    created_by = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_question_banks",
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["subject__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["subject", "name"],
                name="unique_question_bank_per_subject",
            )
        ]

    def __str__(self):
        return f"{self.name} - {self.subject.name}"

class Question(models.Model):
    bank = models.ForeignKey(
        QuestionBank,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="questions",
    )

    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="cbt_questions",
    )

    grade_levels = models.ManyToManyField(
        GradeLevel,
        related_name="cbt_questions",
    )

    topic = models.ForeignKey(
        Topic,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="questions",
    )

    subtopic = models.ForeignKey(
        SubTopic,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="questions",
    )

    question_type = models.CharField(
        max_length=30,
        choices=QuestionType.choices,
    )

    difficulty = models.CharField(
        max_length=20,
        choices=QuestionDifficulty.choices,
        default=QuestionDifficulty.MEDIUM,
    )

    default_marks = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=1,
    )

    status = models.CharField(
        max_length=20,
        choices=QuestionStatus.choices,
        default=QuestionStatus.DRAFT,
    )

    created_by = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_questions",
    )

    current_version = models.ForeignKey(
        "QuestionVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["subject__name", "topic__name", "id"]
        indexes = [
            models.Index(fields=["subject", "status"]),
            models.Index(fields=["question_type", "difficulty"]),
        ]

    def clean(self):
        errors = {}

        if self.bank and self.bank.subject_id != self.subject_id:
            errors["bank"] = (
                "Question bank subject must match the question subject."
            )

        if self.topic and self.topic.subject_id != self.subject_id:
            errors["topic"] = (
                "Topic must belong to the same subject as the question."
            )

        if self.subtopic:
            if not self.topic:
                errors["subtopic"] = (
                    "A topic is required when a subtopic is selected."
                )
            elif self.subtopic.topic_id != self.topic_id:
                errors["subtopic"] = (
                    "Subtopic must belong to the selected topic."
                )

        if self.default_marks <= 0:
            errors["default_marks"] = "Default marks must be greater than zero."

        if errors:
            raise ValidationError(errors)

        super().clean()

    def __str__(self):
        return f"Question #{self.pk} - {self.subject.name}"

class QuestionVersion(models.Model):
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="versions",
    )

    version = models.PositiveIntegerField()

    # Snapshot fields.
    # These preserve how this question version was defined historically.
    question_type = models.CharField(
        max_length=30,
        choices=QuestionType.choices,
    )

    default_marks = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=1,
    )

    text = models.TextField()

    instructions = models.TextField(
        blank=True,
    )

    explanation = models.TextField(
        blank=True,
    )

    created_by = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_question_versions",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["question", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["question", "version"],
                name="unique_question_version",
            )
        ]

    def __str__(self):
        return f"Question {self.question_id} v{self.version}"

    def save(self, *args, **kwargs):
        if self.pk:
            ensure_question_version_mutable(self.pk)
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        ensure_question_version_mutable(self.pk)
        return super().delete(*args, **kwargs)

class QuestionLearningObjective(models.Model):
    question_version = models.ForeignKey(
        QuestionVersion,
        on_delete=models.CASCADE,
        related_name="objective_alignments",
    )

    learning_objective = models.ForeignKey(
        LearningObjective,
        on_delete=models.PROTECT,
        related_name="question_alignments",
    )

    is_primary = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "question_version",
                    "learning_objective",
                ],
                name="unique_question_version_learning_objective",
            ),
            models.UniqueConstraint(
                fields=["question_version"],
                condition=models.Q(is_primary=True),
                name="unique_primary_objective_per_question_version",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "learning_objective",
                    "question_version",
                ]
            ),
        ]

    def __str__(self):
        return (
            f"{self.question_version} → "
            f"{self.learning_objective}"
        )

class QuestionReview(models.Model):

    class Decision(models.TextChoices):
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    question_version = models.ForeignKey(
        QuestionVersion,
        on_delete=models.CASCADE,
        related_name="reviews",
    )

    reviewed_by = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        related_name="question_reviews",
    )

    decision = models.CharField(
        max_length=20,
        choices=Decision.choices,
    )

    comments = models.TextField(
        blank=True,
    )

    reviewed_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-reviewed_at"]

    def __str__(self):
        return (
            f"{self.question_version} - "
            f"{self.get_decision_display()}"
        )

class QuestionAttachment(VersionContentImmutabilityMixin, models.Model):
    question_version = models.ForeignKey(
        QuestionVersion,
        on_delete=models.CASCADE,
        related_name="attachments",
    )

    file = models.FileField(
        upload_to="cbt/question_attachments/%Y/%m/",
    )

    caption = models.CharField(
        max_length=255,
        blank=True,
    )

    order = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"Attachment for {self.question_version}"

    def get_question_version_id(self):
        return self.question_version_id
