from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone

from administration.models import AcademicYear, Term
from .choices import SchemeOfWorkStatus, LessonPlanStatus, LessonDeliveryStatus
from .structure import GradeLevel
from .staff import Teacher, AllocatedSubject
from .curriculum import (
    CurriculumSubject,
    CurriculumTopic,
    SubTopic,
    LearningObjective,
)


class SchemeOfWork(models.Model):
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="schemes_of_work",
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name="schemes_of_work",
    )
    curriculum_subject = models.ForeignKey(
        CurriculumSubject,
        on_delete=models.PROTECT,
        related_name="schemes_of_work",
    )
    created_by = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_schemes_of_work",
    )
    status = models.CharField(
        max_length=20,
        choices=SchemeOfWorkStatus.choices,
        default=SchemeOfWorkStatus.DRAFT,
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_schemes_of_work",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "academic_year",
                    "term",
                    "curriculum_subject",
                ],
                condition=models.Q(is_active=True),
                name="unique_active_scheme_per_term_curriculum_subject",
            )
        ]

    def clean(self):
        errors = {}
        if (
            self.term_id
            and self.academic_year_id
            and self.term.academic_year_id != self.academic_year_id
        ):
            errors["term"] = "Term must belong to the selected academic year."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.curriculum_subject} - {self.academic_year} {self.term}"


class SchemeOfWorkItem(models.Model):
    scheme = models.ForeignKey(
        SchemeOfWork,
        on_delete=models.CASCADE,
        related_name="items",
    )
    week_number = models.PositiveIntegerField()
    curriculum_topic = models.ForeignKey(
        CurriculumTopic,
        on_delete=models.PROTECT,
        related_name="scheme_items",
    )
    subtopics = models.ManyToManyField(
        SubTopic,
        blank=True,
        related_name="scheme_items",
    )
    learning_objectives = models.ManyToManyField(
        LearningObjective,
        blank=True,
        related_name="scheme_items",
    )
    title = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional school-specific lesson/scheme title.",
    )
    notes = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["week_number", "order"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "scheme",
                    "week_number",
                    "order",
                ],
                name="unique_scheme_item_order_per_week",
            )
        ]
        indexes = [
            models.Index(
                fields=[
                    "scheme",
                    "week_number",
                ]
            )
        ]

    def clean(self):
        errors = {}
        if (
            self.scheme_id
            and self.curriculum_topic_id
            and self.curriculum_topic.curriculum_subject_id
            != self.scheme.curriculum_subject_id
        ):
            errors["curriculum_topic"] = (
                "Curriculum topic must belong to the scheme's curriculum subject."
            )
        if self.week_number is not None and self.week_number <= 0:
            errors["week_number"] = "Week number must be greater than zero."
        if errors:
            raise ValidationError(errors)
        super().clean()

    def __str__(self):
        return f"Week {self.week_number} - {self.curriculum_topic.topic.name}"


class LessonPlan(models.Model):
    scheme_item = models.ForeignKey(
        SchemeOfWorkItem,
        on_delete=models.PROTECT,
        related_name="lesson_plans",
    )
    allocation = models.ForeignKey(
        AllocatedSubject,
        on_delete=models.PROTECT,
        related_name="lesson_plans",
    )
    lesson_date = models.DateField()
    title = models.CharField(max_length=255, blank=True)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    learning_objectives = models.ManyToManyField(
        LearningObjective,
        blank=True,
        related_name="lesson_plans",
    )
    subtopics = models.ManyToManyField(
        SubTopic,
        blank=True,
        related_name="lesson_plans",
    )
    previous_knowledge = models.TextField(
        blank=True,
        help_text="Relevant knowledge learners are expected to already have.",
    )
    introduction = models.TextField(blank=True)
    lesson_content = models.TextField(blank=True, help_text="Main lesson notes/content.")
    teacher_activities = models.TextField(blank=True)
    learner_activities = models.TextField(blank=True)
    teaching_materials = models.TextField(blank=True)
    evaluation = models.TextField(
        blank=True,
        help_text="Questions or activities used to assess understanding during/after the lesson.",
    )
    assignment_notes = models.TextField(
        blank=True,
        help_text="Assignment or follow-up work planned for learners after the lesson.",
    )
    references = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=LessonPlanStatus.choices,
        default=LessonPlanStatus.DRAFT,
    )
    rejection_reason = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_lesson_plans",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            "-lesson_date",
            "allocation__class_room",
        ]
        indexes = [
            models.Index(fields=["allocation", "lesson_date"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return (
            self.title
            or f"{self.scheme_item.curriculum_topic.topic.name} - {self.allocation.class_room} - {self.lesson_date}"
        )

    def clean(self):
        errors = {}
        if self.duration_minutes is not None and self.duration_minutes <= 0:
            errors["duration_minutes"] = "Duration must be greater than zero."

        if self.scheme_item_id and self.allocation_id:
            scheme = self.scheme_item.scheme
            curriculum_subject = scheme.curriculum_subject

            if curriculum_subject.subject_id != self.allocation.subject_id:
                errors["allocation"] = "Allocated subject must match the scheme of work subject."

            allocation_grade = self.allocation.class_room.name.grade_level
            if curriculum_subject.grade_level_id != allocation_grade.id:
                errors["allocation"] = "Allocated classroom grade level must match the scheme of work grade level."

            if scheme.academic_year_id != self.allocation.academic_year_id:
                errors["allocation"] = "Allocation academic year must match the scheme of work academic year."

            if self.allocation.term_id and scheme.term_id != self.allocation.term_id:
                errors["allocation"] = "Allocation term must match the scheme of work term."

        if errors:
            raise ValidationError(errors)
        super().clean()


class LessonDelivery(models.Model):
    lesson_plan = models.OneToOneField(
        LessonPlan,
        on_delete=models.PROTECT,
        related_name="delivery",
    )
    status = models.CharField(
        max_length=20,
        choices=LessonDeliveryStatus.choices,
        default=LessonDeliveryStatus.COMPLETED,
    )
    taught_at = models.DateTimeField(default=timezone.now)
    objectives_covered = models.ManyToManyField(
        LearningObjective,
        blank=True,
        related_name="lesson_deliveries",
    )
    subtopics_covered = models.ManyToManyField(
        SubTopic,
        blank=True,
        related_name="lesson_deliveries",
    )
    teacher_notes = models.TextField(
        blank=True,
        help_text="Teacher's notes on how the lesson went, student understanding, challenges, etc.",
    )
    learner_response = models.TextField(
        blank=True,
        help_text="General observations about learner participation and understanding.",
    )
    follow_up_required = models.BooleanField(default=False)
    follow_up_notes = models.TextField(blank=True)
    next_lesson_notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_lesson_deliveries",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.lesson_plan} - {self.get_status_display()}"


class LessonPlanMaterial(models.Model):
    lesson_plan = models.ForeignKey(
        LessonPlan,
        on_delete=models.CASCADE,
        related_name="materials",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    file = models.FileField(
        upload_to="lesson_plans/materials/%Y/%m/",
        blank=True,
        null=True,
    )
    external_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["title"]

    def clean(self):
        errors = {}
        if not self.file and not self.external_url:
            errors["file"] = "Provide either a file or an external URL."
        if self.file and self.external_url:
            errors["external_url"] = "Provide either a file or an external URL, not both."
        if errors:
            raise ValidationError(errors)
        super().clean()

    def __str__(self):
        return f"{self.title} - {self.lesson_plan}"
