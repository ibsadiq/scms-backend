import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import pre_delete

from academic.models import Teacher

from .answer_definitions import (
    FillBlankItem,
    MatchingPair,
    QuestionOption,
)
from .exam import CBTExam, ExamQuestion
from .question_bank import QuestionAttachment, QuestionVersion


FINALIZED_MESSAGE = "Finalized published exam content is immutable."


class PublishedExamRevision(models.Model):
    class Status(models.TextChoices):
        BUILDING = "BUILDING", "Building"
        FINALIZED = "FINALIZED", "Finalized"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    exam = models.ForeignKey(
        CBTExam, on_delete=models.PROTECT, related_name="published_revisions"
    )
    revision_number = models.PositiveIntegerField()
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.BUILDING
    )
    schema_version = models.PositiveIntegerField(default=1)
    content_hash = models.CharField(max_length=64, blank=True)
    title = models.CharField(max_length=255)
    instructions = models.TextField(blank=True)
    duration_minutes = models.PositiveIntegerField()
    shuffle_questions = models.BooleanField(default=True)
    shuffle_options = models.BooleanField(default=True)
    allow_back_navigation = models.BooleanField(default=True)
    auto_submit = models.BooleanField(default=True)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        Teacher,
        on_delete=models.PROTECT,
        related_name="published_cbt_revisions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["exam", "-revision_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["exam", "revision_number"],
                name="unique_published_revision_number_per_exam",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).values(
                "status", "public_id"
            ).first()
            if original and original["status"] == self.Status.FINALIZED:
                raise ValidationError(FINALIZED_MESSAGE)
            if original and original["public_id"] != self.public_id:
                raise ValidationError("Published revision public identity is immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status == self.Status.FINALIZED:
            raise ValidationError(FINALIZED_MESSAGE)
        return super().delete(*args, **kwargs)


class FrozenRevisionContentMixin:
    def get_revision_id(self):
        raise NotImplementedError

    def ensure_mutable(self):
        revision = PublishedExamRevision.objects.only("status").get(
            pk=self.get_revision_id()
        )
        if revision.status == PublishedExamRevision.Status.FINALIZED:
            raise ValidationError(FINALIZED_MESSAGE)

    def save(self, *args, **kwargs):
        self.ensure_mutable()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self.ensure_mutable()
        return super().delete(*args, **kwargs)


class PublishedExamQuestion(FrozenRevisionContentMixin, models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    revision = models.ForeignKey(
        PublishedExamRevision,
        on_delete=models.PROTECT,
        related_name="questions",
    )
    source_exam_question = models.ForeignKey(
        ExamQuestion,
        on_delete=models.PROTECT,
        related_name="published_snapshots",
    )
    source_question_version = models.ForeignKey(
        QuestionVersion,
        on_delete=models.PROTECT,
        related_name="published_snapshots",
    )
    question_type = models.CharField(max_length=30)
    question_text = models.TextField()
    instructions = models.TextField(blank=True)
    marks = models.DecimalField(max_digits=8, decimal_places=2)
    order = models.PositiveIntegerField()
    interaction_config = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["revision", "order"],
                name="unique_published_question_order",
            ),
            models.UniqueConstraint(
                fields=["revision", "source_exam_question"],
                name="unique_source_question_per_revision",
            ),
        ]

    def get_revision_id(self):
        return self.revision_id


class PublishedExamChoice(FrozenRevisionContentMixin, models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    published_question = models.ForeignKey(
        PublishedExamQuestion, on_delete=models.PROTECT, related_name="choices"
    )
    source_option = models.ForeignKey(
        QuestionOption, on_delete=models.PROTECT, null=True, related_name="published_choices"
    )
    key = models.CharField(max_length=40)
    text = models.TextField()
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["published_question", "key"], name="unique_published_choice_key"
            ),
            models.UniqueConstraint(
                fields=["published_question", "order"], name="unique_published_choice_order"
            ),
        ]

    def get_revision_id(self):
        return self.published_question.revision_id


class PublishedExamBlank(FrozenRevisionContentMixin, models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    published_question = models.ForeignKey(
        PublishedExamQuestion, on_delete=models.PROTECT, related_name="blanks"
    )
    source_blank = models.ForeignKey(
        FillBlankItem, on_delete=models.PROTECT, null=True, related_name="published_blanks"
    )
    key = models.CharField(max_length=40)
    position = models.PositiveIntegerField()

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["published_question", "key"], name="unique_published_blank_key"
            ),
            models.UniqueConstraint(
                fields=["published_question", "position"], name="unique_published_blank_position"
            ),
        ]

    def get_revision_id(self):
        return self.published_question.revision_id


class PublishedExamMatchingItem(FrozenRevisionContentMixin, models.Model):
    class Side(models.TextChoices):
        LEFT = "LEFT", "Left"
        RIGHT = "RIGHT", "Right"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    published_question = models.ForeignKey(
        PublishedExamQuestion, on_delete=models.PROTECT, related_name="matching_items"
    )
    source_pair = models.ForeignKey(
        MatchingPair, on_delete=models.PROTECT, null=True, related_name="published_items"
    )
    key = models.CharField(max_length=40)
    side = models.CharField(max_length=5, choices=Side.choices)
    text = models.TextField()
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ["side", "order"]
        constraints = [
            models.UniqueConstraint(
                fields=["published_question", "key"], name="unique_published_matching_key"
            ),
            models.UniqueConstraint(
                fields=["published_question", "side", "order"],
                name="unique_published_matching_order",
            ),
        ]

    def get_revision_id(self):
        return self.published_question.revision_id


class PublishedQuestionGradingDefinition(FrozenRevisionContentMixin, models.Model):
    published_question = models.OneToOneField(
        PublishedExamQuestion,
        on_delete=models.PROTECT,
        related_name="grading_definition",
    )
    definition = models.JSONField(default=dict)

    def get_revision_id(self):
        return self.published_question.revision_id


class PublishedExamMedia(FrozenRevisionContentMixin, models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    published_question = models.ForeignKey(
        PublishedExamQuestion, on_delete=models.PROTECT, related_name="media"
    )
    source_attachment = models.ForeignKey(
        QuestionAttachment, on_delete=models.PROTECT, related_name="published_media"
    )
    filename = models.CharField(max_length=255)
    caption = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField()
    storage_reference = models.TextField()
    content_sha256 = models.CharField(max_length=64)
    size_bytes = models.PositiveBigIntegerField()

    class Meta:
        ordering = ["order"]

    def get_revision_id(self):
        return self.published_question.revision_id


def _prevent_finalized_revision_delete(sender, instance, **kwargs):
    if isinstance(instance, PublishedExamRevision):
        if instance.status == PublishedExamRevision.Status.FINALIZED:
            raise ValidationError(FINALIZED_MESSAGE)
        return
    instance.ensure_mutable()


for _published_model in (
    PublishedExamRevision,
    PublishedExamQuestion,
    PublishedExamChoice,
    PublishedExamBlank,
    PublishedExamMatchingItem,
    PublishedQuestionGradingDefinition,
    PublishedExamMedia,
):
    pre_delete.connect(
        _prevent_finalized_revision_delete,
        sender=_published_model,
        weak=False,
        dispatch_uid=f"cbt.prevent_finalized_delete.{_published_model.__name__}",
    )
