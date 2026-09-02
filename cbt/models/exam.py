from django.db import models
from django.core.exceptions import ValidationError

from academic.models import (
    Subject,
    Topic,
    SubTopic,
    Teacher,
    ClassRoom,
    LearningObjective,
)
from examination.models import AssessmentSession, AssessmentComponent

from .choices import (
    QuestionType,
    QuestionDifficulty,
    CBTExamStatus,
    AttemptExpiryPolicy,
)
from .question_bank import QuestionVersion


class CBTExam(models.Model):
    session = models.ForeignKey(
        AssessmentSession,
        on_delete=models.PROTECT,
        related_name="cbt_exams",
    )

    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name="cbt_exams",
    )

    classroom = models.ForeignKey(
        ClassRoom,
        on_delete=models.PROTECT,
        related_name="cbt_exams",
    )

    component = models.ForeignKey(
        AssessmentComponent,
        on_delete=models.PROTECT,
        related_name="cbt_exams",
    )

    title = models.CharField(
        max_length=200,
        blank=True,
    )

    instructions = models.TextField(
        blank=True,
    )

    duration_minutes = models.PositiveIntegerField()

    available_from = models.DateTimeField(null=True, blank=True)
    available_until = models.DateTimeField(null=True, blank=True)
    attempt_expiry_policy = models.CharField(
        max_length=24,
        choices=AttemptExpiryPolicy.choices,
        default=AttemptExpiryPolicy.CAP_AT_EXAM_CLOSE,
    )

    status = models.CharField(
        max_length=20,
        choices=CBTExamStatus.choices,
        default=CBTExamStatus.DRAFT,
    )

    shuffle_questions = models.BooleanField(default=False)
    shuffle_options = models.BooleanField(default=False)
    allow_back_navigation = models.BooleanField(default=True)
    auto_submit = models.BooleanField(default=True)

    created_by = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_cbt_exams",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "session",
                    "subject",
                    "classroom",
                    "component",
                ],
                name=(
                    "unique_cbt_exam_per_"
                    "session_subject_class_component"
                ),
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(available_from__isnull=True)
                    | models.Q(available_until__isnull=True)
                    | models.Q(available_from__lt=models.F("available_until"))
                ),
                name="cbt_exam_valid_availability_interval",
            ),
        ]
        indexes = [
            models.Index(
                fields=[
                    "session",
                    "classroom",
                    "subject",
                ]
            ),
            models.Index(
                fields=["status"]
            ),
        ]

    def clean(self):
        errors = {}

        if (
            self.duration_minutes is not None
            and self.duration_minutes <= 0
        ):
            errors["duration_minutes"] = (
                "Duration must be greater than zero."
            )

        if (
            self.available_from
            and self.available_until
            and self.available_from >= self.available_until
        ):
            errors["available_until"] = "Availability end must be after its start."

        if (
            self.session_id
            and self.classroom_id
            and not self.session.classrooms.filter(
                pk=self.classroom_id
            ).exists()
        ):
            errors["classroom"] = (
                "Classroom must be included in the "
                "assessment session."
            )

        if errors:
            raise ValidationError(errors)

        super().clean()

    def __str__(self):
        if self.title:
            return self.title

        return (
            f"{self.session.name} - "
            f"{self.subject.name} - "
            f"{self.classroom}"
        )

class ExamBlueprint(models.Model):
    cbt_exam = models.OneToOneField(
        CBTExam,
        on_delete=models.CASCADE,
        related_name="blueprint",
    )

    is_locked = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def total_questions(self):
        return (
            self.rules.aggregate(
                total=models.Sum("question_count")
            )["total"]
            or 0
        )

    @property
    def generated_question_count(self):
        return self.cbt_exam.exam_questions.count()

    @property
    def is_generated(self):
        return self.generated_question_count > 0

    def __str__(self):
        return f"Blueprint - {self.cbt_exam}"

class BlueprintRule(models.Model):
    blueprint = models.ForeignKey(
        ExamBlueprint,
        on_delete=models.CASCADE,
        related_name="rules",
    )

    topic = models.ForeignKey(
        Topic,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="blueprint_rules",
    )

    subtopic = models.ForeignKey(
        SubTopic,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="blueprint_rules",
    )

    learning_objective = models.ForeignKey(
        LearningObjective,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="blueprint_rules",
    )

    question_type = models.CharField(
        max_length=30,
        choices=QuestionType.choices,
        blank=True,
    )

    difficulty = models.CharField(
        max_length=20,
        choices=QuestionDifficulty.choices,
        blank=True,
    )

    question_count = models.PositiveIntegerField()

    order = models.PositiveIntegerField(
        default=1,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["order", "id"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "blueprint",
                    "order",
                ],
                name="unique_blueprint_rule_order",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "blueprint",
                    "topic",
                    "subtopic",
                ]
            ),
            models.Index(
                fields=[
                    "question_type",
                    "difficulty",
                ]
            ),
        ]

    def clean(self):
        errors = {}

        if (
            self.question_count is not None
            and self.question_count <= 0
        ):
            errors["question_count"] = (
                "Question count must be greater than zero."
            )

        if self.blueprint_id and self.blueprint.is_locked:
            errors["blueprint"] = (
                "A locked blueprint cannot be modified."
            )

        if self.subtopic_id:
            if not self.topic_id:
                errors["subtopic"] = (
                    "A topic is required when a subtopic "
                    "is selected."
                )
            elif self.subtopic.topic_id != self.topic_id:
                errors["subtopic"] = (
                    "Subtopic must belong to the "
                    "selected topic."
                )

        if (
            self.learning_objective_id
            and self.topic_id
        ):
            objective_topic_id = (
                self.learning_objective
                .curriculum_topic
                .topic_id
            )

            if objective_topic_id != self.topic_id:
                errors["learning_objective"] = (
                    "Learning objective must belong to "
                    "the selected topic."
                )

        if (
            self.learning_objective_id
            and self.subtopic_id
            and self.learning_objective.subtopic_id
            and self.learning_objective.subtopic_id
            != self.subtopic_id
        ):
            errors["learning_objective"] = (
                "Learning objective must belong to "
                "the selected subtopic."
            )

        if errors:
            raise ValidationError(errors)

        super().clean()

    def __str__(self):
        criteria = []

        if self.topic_id:
            criteria.append(self.topic.name)

        if self.subtopic_id:
            criteria.append(self.subtopic.name)

        if self.learning_objective_id:
            criteria.append(
                self.learning_objective.description[:50]
            )

        if self.question_type:
            criteria.append(
                self.get_question_type_display()
            )

        if self.difficulty:
            criteria.append(
                self.get_difficulty_display()
            )

        description = (
            " / ".join(criteria)
            if criteria
            else "Any eligible question"
        )

        return (
            f"{self.blueprint.cbt_exam} - "
            f"{description} ({self.question_count})"
        )

class ExamQuestion(models.Model):
    cbt_exam = models.ForeignKey(
        CBTExam,
        on_delete=models.CASCADE,
        related_name="exam_questions",
    )

    question_version = models.ForeignKey(
        QuestionVersion,
        on_delete=models.PROTECT,
        related_name="exam_questions",
    )

    blueprint_rule = models.ForeignKey(
        BlueprintRule,
        on_delete=models.PROTECT,
        related_name="exam_questions",
        null=True,
        blank=True,
    )

    order = models.PositiveIntegerField()

    marks = models.DecimalField(
        max_digits=6,
        decimal_places=2,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["order"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "cbt_exam",
                    "order",
                ],
                name="unique_exam_question_order",
            ),

            models.UniqueConstraint(
                fields=[
                    "cbt_exam",
                    "question_version",
                ],
                name="unique_question_version_per_exam",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "cbt_exam",
                    "order",
                ]
            ),
            models.Index(
                fields=[
                    "cbt_exam",
                    "blueprint_rule",
                ]
            ),
        ]

    def clean(self):
        errors = {}

        if self.order is not None and self.order <= 0:
            errors["order"] = (
                "Question order must be greater than zero."
            )

        if self.marks is not None and self.marks <= 0:
            errors["marks"] = (
                "Question marks must be greater than zero."
            )

        if (
            self.blueprint_rule_id
            and self.blueprint_rule.blueprint.cbt_exam_id
            != self.cbt_exam_id
        ):
            errors["blueprint_rule"] = (
                "Blueprint rule must belong to the "
                "same CBT exam."
            )

        if errors:
            raise ValidationError(errors)

        super().clean()

    def __str__(self):
        return (
            f"{self.cbt_exam} - "
            f"Question {self.order}"
        )
