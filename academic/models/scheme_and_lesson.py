from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.conf import settings

from administration.models import AcademicYear, Term
from .choices import (
    LessonDeliveryStatus,
    LessonPlanStatus,
    PublishedSchemeEntryType,
    SchemeOfWorkStatus,
)
from .structure import GradeLevel
from .staff import Teacher, AllocatedSubject
from .curriculum import (
    CurriculumSubject,
    CurriculumTopic,
    SubTopic,
    LearningObjective,
    PublishedSchemeEntry,
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
    responsible_teacher = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=False,
        related_name="responsible_schemes_of_work",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
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
        indexes = [
            models.Index(fields=["responsible_teacher"], name="acad_sow_resp_teacher_idx"),
        ]
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
    published_scheme_entry = models.ForeignKey(
        PublishedSchemeEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adopted_scheme_items",
    )
    entry_type = models.CharField(
        max_length=20,
        choices=PublishedSchemeEntryType.choices,
        default=PublishedSchemeEntryType.INSTRUCTION,
    )
    week_start = models.PositiveIntegerField(null=True, blank=True)
    week_end = models.PositiveIntegerField(null=True, blank=True)
    curriculum_topic = models.ForeignKey(
        CurriculumTopic,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
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
    content_summary = models.TextField(blank=True)
    teacher_activities = models.TextField(blank=True)
    learner_activities = models.TextField(blank=True)
    learning_resources = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "week_start", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["scheme", "order"],
                name="unique_scheme_item_order",
            ),
            models.UniqueConstraint(
                fields=["scheme", "published_scheme_entry"],
                condition=models.Q(published_scheme_entry__isnull=False),
                name="unique_adopted_entry_per_scheme",
            ),
            models.CheckConstraint(
                condition=models.Q(week_start__isnull=True) | models.Q(week_start__gt=0),
                name="scheme_item_week_start_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(week_end__isnull=True) | models.Q(week_end__gt=0),
                name="scheme_item_week_end_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(week_end__isnull=True)
                    | (
                        models.Q(week_start__isnull=False)
                        & models.Q(week_end__gte=models.F("week_start"))
                    )
                ),
                name="scheme_item_week_range_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=["scheme", "week_start", "order"],
                name="scheme_item_week_order_idx",
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
        if self.entry_type == PublishedSchemeEntryType.INSTRUCTION and not self.curriculum_topic_id:
            errors["curriculum_topic"] = "Instructional entries require a curriculum topic."
        if self.entry_type in {PublishedSchemeEntryType.BREAK, PublishedSchemeEntryType.CLOSING} and self.curriculum_topic_id:
            errors["curriculum_topic"] = "Break and closing entries cannot have a curriculum topic."
        if self.week_start is not None and self.week_start <= 0:
            errors["week_start"] = "Week start must be greater than zero."
        if self.week_end is not None:
            if self.week_start is None:
                errors["week_end"] = "Week start is required when week end is provided."
            elif self.week_end < self.week_start:
                errors["week_end"] = "Week end cannot be less than week start."
        if (
            self.published_scheme_entry_id
            and self.scheme_id
            and self.published_scheme_entry.published_scheme.curriculum_subject_id
            != self.scheme.curriculum_subject_id
        ):
            errors["published_scheme_entry"] = "Source entry must match the scheme curriculum subject."
        if errors:
            raise ValidationError(errors)
        super().clean()

    def __str__(self):
        placement = "Unscheduled" if self.week_start is None else f"Week {self.week_start}"
        if self.week_end and self.week_end != self.week_start:
            placement = f"Weeks {self.week_start}-{self.week_end}"
        label = self.title or (self.curriculum_topic.name if self.curriculum_topic_id else self.get_entry_type_display())
        return f"{placement} - {label}"


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
            or f"{self.scheme_item.curriculum_topic.name if self.scheme_item.curriculum_topic_id else self.scheme_item.get_entry_type_display()} - {self.allocation.class_room} - {self.lesson_date}"
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

            allocation_grade = self.allocation.class_room.grade_level
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
    content = models.TextField(
        blank=True,
        help_text="Textual lesson material such as notes, examples, or instructions.",
    )
    file = models.FileField(
        upload_to="lesson_plans/materials/%Y/%m/",
        blank=True,
        null=True,
    )
    external_url = models.URLField(blank=True)
    source_curriculum_resource = models.ForeignKey(
        "academic.CurriculumResource",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lesson_plan_material_copies",
    )
    source_resource_title = models.CharField(max_length=255, blank=True)
    source_resource_type = models.CharField(max_length=30, blank=True)
    source_curriculum_name = models.CharField(max_length=255, blank=True)
    source_curriculum_version = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["title"]
        constraints = [
            models.UniqueConstraint(
                fields=["lesson_plan", "source_curriculum_resource"],
                condition=models.Q(source_curriculum_resource__isnull=False),
                name="unique_curriculum_resource_per_lesson_plan",
            )
        ]

    def clean(self):
        errors = {}
        if not self.file and not self.external_url and not (self.content or "").strip():
            errors["file"] = "Provide a file, external URL, or textual content."
        if self.file and self.external_url:
            errors["external_url"] = "Provide either a file or an external URL, not both."
        if errors:
            raise ValidationError(errors)
        super().clean()

    def __str__(self):
        return f"{self.title} - {self.lesson_plan}"
