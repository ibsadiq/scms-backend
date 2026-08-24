from django.db import models
from django.core.exceptions import ValidationError

from .choices import CurriculumAuthority
from .structure import GradeLevel
from .staff import Subject


class Curriculum(models.Model):
    name = models.CharField(max_length=200)
    authority_type = models.CharField(
        max_length=20,
        choices=CurriculumAuthority.choices,
        default=CurriculumAuthority.NERDC,
    )
    authority_name = models.CharField(
        max_length=200,
        blank=True,
        help_text=(
            "Issuing authority, e.g. Nigerian Educational "
            "Research and Development Council."
        ),
    )
    version = models.CharField(
        max_length=100,
        blank=True,
        help_text="Curriculum edition/version if applicable.",
    )
    description = models.TextField(blank=True)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-effective_from", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "version"],
                name="unique_curriculum_name_version",
            )
        ]

    def clean(self):
        errors = {}
        if (
            self.effective_from
            and self.effective_to
            and self.effective_to < self.effective_from
        ):
            errors["effective_to"] = (
                "Effective end date cannot be earlier than the start date."
            )
        if errors:
            raise ValidationError(errors)
        super().clean()

    def __str__(self):
        if self.version:
            return f"{self.name} ({self.version})"
        return self.name


class CurriculumSubject(models.Model):
    curriculum = models.ForeignKey(
        Curriculum,
        on_delete=models.CASCADE,
        related_name="subjects",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name="curriculum_subjects",
    )
    grade_level = models.ForeignKey(
        GradeLevel,
        on_delete=models.PROTECT,
        related_name="curriculum_subjects",
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            "grade_level__sequence_order",
            "subject__name",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "curriculum",
                    "subject",
                    "grade_level",
                ],
                name="unique_curriculum_subject_grade",
            )
        ]
        indexes = [
            models.Index(
                fields=[
                    "curriculum",
                    "grade_level",
                    "subject",
                ]
            )
        ]

    def __str__(self):
        return (
            f"{self.curriculum} - "
            f"{self.subject.name} - "
            f"{self.grade_level}"
        )


class Topic(models.Model):
    name = models.CharField(max_length=255)
    grade_level = models.ForeignKey(
        GradeLevel,
        on_delete=models.CASCADE,
        related_name="topics",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="topics",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["grade_level__sequence_order", "subject__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["grade_level", "subject", "name"],
                name="unique_topic_per_grade_subject",
            )
        ]
        indexes = [
            models.Index(fields=["grade_level", "subject"]),
        ]

    def __str__(self):
        return f"{self.name} - {self.subject.name} ({self.grade_level})"


class CurriculumTopic(models.Model):
    curriculum_subject = models.ForeignKey(
        CurriculumSubject,
        on_delete=models.CASCADE,
        related_name="curriculum_topics",
    )
    topic = models.ForeignKey(
        Topic,
        on_delete=models.PROTECT,
        related_name="curriculum_mappings",
    )
    theme = models.CharField(
        max_length=255,
        blank=True,
        help_text=(
            "Optional curriculum theme/strand under which "
            "the topic is organised."
        ),
    )
    content_summary = models.TextField(
        blank=True,
        help_text="Curriculum-specific content or scope for this topic.",
    )
    order = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "topic__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["curriculum_subject", "topic"],
                name="unique_topic_per_curriculum_subject",
            ),
            models.UniqueConstraint(
                fields=["curriculum_subject", "order"],
                name="unique_curriculum_topic_order",
            ),
        ]

    def clean(self):
        errors = {}
        if self.curriculum_subject_id and self.topic_id:
            if self.topic.subject_id != self.curriculum_subject.subject_id:
                errors["topic"] = "Topic subject must match the curriculum subject."
            if self.topic.grade_level_id != self.curriculum_subject.grade_level_id:
                errors["topic"] = "Topic grade level must match the curriculum subject grade level."
        if errors:
            raise ValidationError(errors)
        super().clean()

    def __str__(self):
        return f"{self.topic.name} - {self.curriculum_subject}"


class CurriculumGuidance(models.Model):
    curriculum_topic = models.OneToOneField(
        CurriculumTopic,
        on_delete=models.CASCADE,
        related_name="guidance",
    )
    teacher_activities = models.TextField(blank=True)
    learner_activities = models.TextField(blank=True)
    teaching_learning_materials = models.TextField(blank=True)
    evaluation_guide = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Guidance - {self.curriculum_topic}"


class SubTopic(models.Model):
    name = models.CharField(max_length=255)
    topic = models.ForeignKey(
        Topic,
        on_delete=models.CASCADE,
        related_name="subtopics",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["topic__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["topic", "name"],
                name="unique_subtopic_per_topic",
            )
        ]
        indexes = [
            models.Index(fields=["topic"]),
        ]

    def __str__(self):
        return f"{self.name} - {self.topic.name}"


class LearningObjective(models.Model):
    curriculum_topic = models.ForeignKey(
        CurriculumTopic,
        on_delete=models.CASCADE,
        related_name="learning_objectives",
    )
    subtopic = models.ForeignKey(
        SubTopic,
        on_delete=models.PROTECT,
        related_name="learning_objectives",
        null=True,
        blank=True,
    )
    description = models.TextField()
    order = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["curriculum_topic", "order"],
                name="unique_learning_objective_order",
            )
        ]

    def clean(self):
        errors = {}
        if (
            self.subtopic_id
            and self.curriculum_topic_id
            and self.subtopic.topic_id != self.curriculum_topic.topic_id
        ):
            errors["subtopic"] = "Subtopic must belong to the curriculum topic."
        if errors:
            raise ValidationError(errors)
        super().clean()

    def __str__(self):
        return f"LO {self.order} - {self.curriculum_topic.topic.name}"
