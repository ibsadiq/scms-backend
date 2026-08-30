import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from .choices import (
    CurriculumAuthority,
    CurriculumResourceType,
    PublishedSchemeEntryType,
)
from .structure import GradeLevel
from .staff import Subject


class SourceType(models.TextChoices):
    PDF = "PDF", "PDF Document"
    DOCX = "DOCX", "Word Document"
    XLSX = "XLSX", "Excel Spreadsheet"
    MANUAL = "MANUAL", "Manual Entry / Structured JSON"
    OTHER = "OTHER", "Other Source"


class ImportBatchStatus(models.TextChoices):
    STARTED = "STARTED", "Started"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


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


class CurriculumSource(models.Model):
    """Authoritative source document from which curriculum content was extracted."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    curriculum = models.ForeignKey(
        Curriculum,
        on_delete=models.CASCADE,
        related_name="sources",
    )
    title = models.CharField(max_length=255)
    authority = models.CharField(max_length=200, blank=True)
    publication_year = models.PositiveSmallIntegerField(null=True, blank=True)
    version = models.CharField(max_length=100, blank=True)
    original_filename = models.CharField(max_length=255, blank=True)
    source_type = models.CharField(
        max_length=20,
        choices=SourceType.choices,
        default=SourceType.PDF,
    )
    source_reference = models.CharField(
        max_length=255,
        blank=True,
        help_text="Official ISBN, Gazette number, or regulatory circular reference.",
    )
    checksum_sha256 = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="Deterministic SHA-256 checksum of the original source document.",
    )
    file = models.FileField(
        upload_to="curriculum_sources/%Y/%m/",
        null=True,
        blank=True,
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_curriculum_sources",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "title"]
        constraints = [
            models.UniqueConstraint(
                fields=["curriculum", "checksum_sha256"],
                condition=~Q(checksum_sha256=""),
                name="unique_curriculum_source_checksum",
            )
        ]

    def clean(self):
        errors = {}
        if self.checksum_sha256:
            clean_hash = self.checksum_sha256.strip().lower()
            if len(clean_hash) != 64:
                errors["checksum_sha256"] = "SHA-256 checksum must be exactly 64 hexadecimal characters."
            else:
                try:
                    int(clean_hash, 16)
                    self.checksum_sha256 = clean_hash
                except ValueError:
                    errors["checksum_sha256"] = "SHA-256 checksum must contain only valid hexadecimal digits."

        if errors:
            raise ValidationError(errors)
        super().clean()

    def __str__(self):
        return f"{self.title} ({self.version or self.publication_year or 'N/A'})"


class CurriculumImportBatch(models.Model):
    """Audit record for a single live curriculum content ingestion execution."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    curriculum = models.ForeignKey(
        Curriculum,
        on_delete=models.CASCADE,
        related_name="import_batches",
    )
    source = models.ForeignKey(
        CurriculumSource,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="import_batches",
    )
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="curriculum_import_batches",
    )
    status = models.CharField(
        max_length=20,
        choices=ImportBatchStatus.choices,
        default=ImportBatchStatus.STARTED,
        db_index=True,
    )
    source_checksum = models.CharField(max_length=64, blank=True)
    grade_filter = models.CharField(max_length=50, blank=True)
    subject_filter = models.CharField(max_length=100, blank=True)
    summary = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured entity metric counts (CREATED, UPDATED, REUSED, UNCHANGED).",
    )
    errors = models.JSONField(default=list, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def clean(self):
        errors = {}
        if self.source_id and self.curriculum_id and self.source.curriculum_id != self.curriculum_id:
            errors["source"] = "Source curriculum must match batch curriculum."
        if errors:
            raise ValidationError(errors)
        super().clean()

    def __str__(self):
        return f"Batch #{self.id} - {self.curriculum.name} [{self.status}]"


class CurriculumSubject(models.Model):
    curriculum = models.ForeignKey(
        Curriculum,
        on_delete=models.CASCADE,
        related_name="subjects",
    )
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, blank=True)
    subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
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
            "name",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "curriculum",
                    "name",
                    "grade_level",
                ],
                name="unique_curriculum_subject_name_grade",
            )
        ]
        indexes = [
            models.Index(
                fields=[
                    "curriculum",
                    "grade_level",
                    "name",
                ]
            ),
            models.Index(fields=["subject"]),
        ]

    def clean(self):
        super().clean()
        if not self.name and self.subject:
            self.name = self.subject.name
        if not self.code and self.subject:
            self.code = self.subject.subject_code or ""

    def save(self, *args, **kwargs):
        if not self.name and self.subject:
            self.name = self.subject.name
        if not self.code and self.subject:
            self.code = self.subject.subject_code or ""
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.curriculum} - "
            f"{self.name} - "
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


class SubTopic(models.Model):
    name = models.CharField(max_length=255)
    topic = models.ForeignKey(
        Topic,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subtopics",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
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
        return self.name


class CurriculumTopic(models.Model):
    curriculum_subject = models.ForeignKey(
        CurriculumSubject,
        on_delete=models.CASCADE,
        related_name="curriculum_topics",
    )
    name = models.CharField(max_length=255)
    topic = models.ForeignKey(
        Topic,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="curriculum_mappings",
    )
    subtopics = models.ManyToManyField(
        SubTopic,
        blank=True,
        related_name="curriculum_topics",
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

    # ── Provenance & Citations
    source = models.ForeignKey(
        CurriculumSource,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="curriculum_topics",
    )
    source_page_start = models.PositiveIntegerField(null=True, blank=True)
    source_page_end = models.PositiveIntegerField(null=True, blank=True)
    source_reference = models.CharField(max_length=255, blank=True)
    last_import_batch = models.ForeignKey(
        CurriculumImportBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="curriculum_topics",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["curriculum_subject", "name"],
                name="unique_topic_name_per_curriculum_subject",
            ),
            models.UniqueConstraint(
                fields=["curriculum_subject", "order"],
                name="unique_curriculum_topic_order",
            ),
        ]

    def clean(self):
        super().clean()
        if not self.name and self.topic:
            self.name = self.topic.name
        errors = {}
        if self.curriculum_subject_id and self.topic_id:
            if (
                self.topic.subject_id
                and self.curriculum_subject.subject_id
                and self.topic.subject_id != self.curriculum_subject.subject_id
            ):
                errors["topic"] = "Topic subject must match the curriculum subject."
            if self.topic.grade_level_id != self.curriculum_subject.grade_level_id:
                errors["topic"] = "Topic grade level must match the curriculum subject grade level."

        if self.source_page_start is not None and self.source_page_start <= 0:
            errors["source_page_start"] = "Page start must be a positive integer."
        if self.source_page_end is not None and self.source_page_end <= 0:
            errors["source_page_end"] = "Page end must be a positive integer."
        if (
            self.source_page_start is not None
            and self.source_page_end is not None
            and self.source_page_end < self.source_page_start
        ):
            errors["source_page_end"] = "Page end cannot be less than page start."

        if (
            self.source_id
            and self.curriculum_subject_id
            and self.source.curriculum_id != self.curriculum_subject.curriculum_id
        ):
            errors["source"] = "Source curriculum must match curriculum subject curriculum."

        if errors:
            raise ValidationError(errors)
        super().clean()

    def save(self, *args, **kwargs):
        if not self.name and self.topic:
            self.name = self.topic.name
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} - {self.curriculum_subject}"


class CurriculumGuidance(models.Model):
    """Invariant guidance that applies to a curriculum topic as a whole."""
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


class LearningObjective(models.Model):
    curriculum_topic = models.ForeignKey(
        CurriculumTopic,
        on_delete=models.CASCADE,
        related_name="learning_objectives",
    )
    subtopic = models.ForeignKey(
        SubTopic,
        on_delete=models.SET_NULL,
        related_name="learning_objectives",
        null=True,
        blank=True,
    )
    description = models.TextField()
    order = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    # ── Provenance & Citations
    source_page = models.PositiveIntegerField(null=True, blank=True)
    source_reference = models.CharField(max_length=255, blank=True)
    last_import_batch = models.ForeignKey(
        CurriculumImportBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="learning_objectives",
    )

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

        if self.source_page is not None and self.source_page <= 0:
            errors["source_page"] = "Source page must be a positive integer."

        if errors:
            raise ValidationError(errors)
        super().clean()

    def __str__(self):
        return f"LO {self.order} - {self.curriculum_topic.name}"


class PublishedScheme(models.Model):
    """An official publisher-provided scheme for one curriculum subject."""

    curriculum_subject = models.ForeignKey(
        CurriculumSubject,
        on_delete=models.CASCADE,
        related_name="published_schemes",
    )
    name = models.CharField(max_length=200, default="Published Scheme of Work")
    version = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    source = models.ForeignKey(
        CurriculumSource,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_schemes",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["curriculum_subject", "name", "version"]
        constraints = [
            models.UniqueConstraint(
                fields=["curriculum_subject", "name", "version"],
                name="unique_published_scheme_version",
            )
        ]

    def clean(self):
        errors = {}
        if (
            self.source_id
            and self.curriculum_subject_id
            and self.source.curriculum_id
            != self.curriculum_subject.curriculum_id
        ):
            errors["source"] = "Source curriculum must match the curriculum subject curriculum."
        if errors:
            raise ValidationError(errors)
        super().clean()

    def __str__(self):
        suffix = f" ({self.version})" if self.version else ""
        return f"{self.name}{suffix} - {self.curriculum_subject}"


class PublishedSchemeEntry(models.Model):
    """One row or placement in an official published scheme of work."""

    published_scheme = models.ForeignKey(
        PublishedScheme,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    term_number = models.PositiveSmallIntegerField()
    week_start = models.PositiveSmallIntegerField(null=True, blank=True)
    week_end = models.PositiveSmallIntegerField(null=True, blank=True)
    entry_type = models.CharField(
        max_length=20,
        choices=PublishedSchemeEntryType.choices,
        default=PublishedSchemeEntryType.INSTRUCTION,
    )
    curriculum_topic = models.ForeignKey(
        CurriculumTopic,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_scheme_entries",
    )
    subtopics = models.ManyToManyField(
        SubTopic,
        blank=True,
        related_name="published_scheme_entries",
    )
    learning_objectives = models.ManyToManyField(
        LearningObjective,
        blank=True,
        related_name="published_scheme_entries",
    )
    title = models.CharField(max_length=255, blank=True)
    content_summary = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=1)
    teacher_activities = models.TextField(blank=True)
    pupil_activities = models.TextField(blank=True)
    learning_resources = models.TextField(blank=True)
    source = models.ForeignKey(
        CurriculumSource,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_scheme_entries",
    )
    source_page_start = models.PositiveIntegerField(null=True, blank=True)
    source_page_end = models.PositiveIntegerField(null=True, blank=True)
    source_reference = models.CharField(max_length=255, blank=True)
    import_batch = models.ForeignKey(
        CurriculumImportBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_scheme_entries",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["term_number", "order", "week_start", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["published_scheme", "term_number", "order"],
                name="unique_published_scheme_term_order",
            )
        ]
        indexes = [
            models.Index(fields=["published_scheme", "term_number", "week_start"]),
        ]

    def clean(self):
        errors = {}
        if self.term_number not in {1, 2, 3}:
            errors["term_number"] = "Term number must be 1, 2, or 3."
        if self.week_start is not None and self.week_start < 1:
            errors["week_start"] = "Week start must be at least 1."
        if self.week_end is not None:
            if self.week_start is None:
                errors["week_end"] = "Week start is required when week end is provided."
            elif self.week_end < self.week_start:
                errors["week_end"] = "Week end cannot be less than week start."
        if (
            self.curriculum_topic_id
            and self.published_scheme_id
            and self.curriculum_topic.curriculum_subject_id
            != self.published_scheme.curriculum_subject_id
        ):
            errors["curriculum_topic"] = (
                "Curriculum topic must belong to the published scheme's curriculum subject."
            )
        curriculum_id = None
        if self.published_scheme_id:
            curriculum_id = self.published_scheme.curriculum_subject.curriculum_id
        if self.source_id and curriculum_id and self.source.curriculum_id != curriculum_id:
            errors["source"] = "Source curriculum must match the published scheme curriculum."
        if self.import_batch_id and curriculum_id and self.import_batch.curriculum_id != curriculum_id:
            errors["import_batch"] = "Import batch curriculum must match the published scheme curriculum."
        if self.source_page_start is not None and self.source_page_start < 1:
            errors["source_page_start"] = "Page start must be at least 1."
        if self.source_page_end is not None:
            if self.source_page_start is None:
                errors["source_page_end"] = "Page start is required when page end is provided."
            elif self.source_page_end < self.source_page_start:
                errors["source_page_end"] = "Page end cannot be less than page start."
        if errors:
            raise ValidationError(errors)
        super().clean()

    def __str__(self):
        week = "Unscheduled" if self.week_start is None else f"Week {self.week_start}"
        if self.week_end is not None and self.week_end != self.week_start:
            week = f"Weeks {self.week_start}-{self.week_end}"
        return f"Term {self.term_number}, {week}: {self.title or self.get_entry_type_display()}"


class CurriculumResource(models.Model):
    """A flexible official reference or instructional curriculum resource."""

    curriculum_subject = models.ForeignKey(
        CurriculumSubject,
        on_delete=models.CASCADE,
        related_name="resources",
    )
    curriculum_topic = models.ForeignKey(
        CurriculumTopic,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="resources",
    )
    published_scheme_entry = models.ForeignKey(
        PublishedSchemeEntry,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="resources",
    )
    resource_type = models.CharField(
        max_length=30,
        choices=CurriculumResourceType.choices,
        default=CurriculumResourceType.OTHER,
    )
    title = models.CharField(max_length=255)
    content = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    order = models.PositiveIntegerField(default=1)
    source = models.ForeignKey(
        CurriculumSource,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="curriculum_resources",
    )
    source_page_start = models.PositiveIntegerField(null=True, blank=True)
    source_page_end = models.PositiveIntegerField(null=True, blank=True)
    source_reference = models.CharField(max_length=255, blank=True)
    import_batch = models.ForeignKey(
        CurriculumImportBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="curriculum_resources",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["curriculum_subject", "order", "title", "id"]
        indexes = [
            models.Index(fields=["curriculum_subject", "resource_type", "is_active"]),
        ]

    def clean(self):
        errors = {}
        if (
            self.curriculum_topic_id
            and self.curriculum_topic.curriculum_subject_id != self.curriculum_subject_id
        ):
            errors["curriculum_topic"] = "Curriculum topic must belong to the curriculum subject."
        if (
            self.published_scheme_entry_id
            and self.published_scheme_entry.published_scheme.curriculum_subject_id
            != self.curriculum_subject_id
        ):
            errors["published_scheme_entry"] = (
                "Published scheme entry must belong to the curriculum subject."
            )
        if (
            self.curriculum_topic_id
            and self.published_scheme_entry_id
            and self.published_scheme_entry.curriculum_topic_id
            and self.published_scheme_entry.curriculum_topic_id != self.curriculum_topic_id
        ):
            errors["published_scheme_entry"] = (
                "Published scheme entry topic must match the resource curriculum topic."
            )
        curriculum_id = self.curriculum_subject.curriculum_id if self.curriculum_subject_id else None
        if self.source_id and curriculum_id and self.source.curriculum_id != curriculum_id:
            errors["source"] = "Source curriculum must match the curriculum subject curriculum."
        if self.import_batch_id and curriculum_id and self.import_batch.curriculum_id != curriculum_id:
            errors["import_batch"] = "Import batch curriculum must match the curriculum subject curriculum."
        if self.source_page_start is not None and self.source_page_start < 1:
            errors["source_page_start"] = "Page start must be at least 1."
        if self.source_page_end is not None:
            if self.source_page_start is None:
                errors["source_page_end"] = "Page start is required when page end is provided."
            elif self.source_page_end < self.source_page_start:
                errors["source_page_end"] = "Page end cannot be less than page start."
        if errors:
            raise ValidationError(errors)
        super().clean()

    def __str__(self):
        return f"{self.get_resource_type_display()}: {self.title}"
