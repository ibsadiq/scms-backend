from decimal import Decimal

from django.db import models
from django.core.exceptions import ValidationError

from .question_bank import QuestionVersion
from .immutability import VersionContentImmutabilityMixin


class QuestionOption(VersionContentImmutabilityMixin, models.Model):
    question_version = models.ForeignKey(
        QuestionVersion,
        on_delete=models.CASCADE,
        related_name="options",
    )

    text = models.TextField()

    is_correct = models.BooleanField(default=False)

    order = models.PositiveIntegerField(default=1)

    feedback = models.TextField(blank=True)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["question_version", "order"],
                name="unique_option_order_per_question_version",
            )
        ]

    def __str__(self):
        return f"Option {self.order} - Q{self.question_version.question_id}"

    def get_question_version_id(self):
        return self.question_version_id

class ShortAnswerDefinition(VersionContentImmutabilityMixin, models.Model):
    question_version = models.OneToOneField(
        "QuestionVersion",
        on_delete=models.CASCADE,
        related_name="short_answer_definition",
    )

    case_sensitive = models.BooleanField(default=False)
    trim_whitespace = models.BooleanField(default=True)

    def __str__(self):
        return f"Short answer config - {self.question_version}"

    def get_question_version_id(self):
        return self.question_version_id

class ShortAnswerVariant(VersionContentImmutabilityMixin, models.Model):
    definition = models.ForeignKey(
        ShortAnswerDefinition,
        on_delete=models.CASCADE,
        related_name="accepted_answers",
    )

    answer = models.CharField(max_length=500)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["definition", "answer"],
                name="unique_short_answer_variant",
            )
        ]

    def __str__(self):
        return self.answer

    def get_question_version_id(self):
        return self.definition.question_version_id

class NumericAnswerDefinition(VersionContentImmutabilityMixin, models.Model):
    question_version = models.OneToOneField(
        "QuestionVersion",
        on_delete=models.CASCADE,
        related_name="numeric_answer_definition",
    )

    expected_value = models.DecimalField(
        max_digits=18,
        decimal_places=6,
    )

    tolerance = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=Decimal("0"),
        help_text="Accepted absolute deviation from the expected value.",
    )

    def clean(self):
        if self.tolerance < 0:
            raise ValidationError(
                {"tolerance": "Tolerance cannot be negative."}
            )

        super().clean()

    def __str__(self):
        return f"{self.expected_value} ± {self.tolerance}"

    def get_question_version_id(self):
        return self.question_version_id

class FillBlankDefinition(VersionContentImmutabilityMixin, models.Model):
    question_version = models.OneToOneField(
        "QuestionVersion",
        on_delete=models.CASCADE,
        related_name="fill_blank_definition",
    )

    case_sensitive = models.BooleanField(default=False)

    def __str__(self):
        return f"Fill blank config - {self.question_version}"

    def get_question_version_id(self):
        return self.question_version_id

class FillBlankItem(VersionContentImmutabilityMixin, models.Model):
    definition = models.ForeignKey(
        FillBlankDefinition,
        on_delete=models.CASCADE,
        related_name="blanks",
    )

    position = models.PositiveIntegerField()

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["definition", "position"],
                name="unique_blank_position",
            )
        ]

    def get_question_version_id(self):
        return self.definition.question_version_id

class FillBlankAcceptedAnswer(VersionContentImmutabilityMixin, models.Model):
    blank = models.ForeignKey(
        FillBlankItem,
        on_delete=models.CASCADE,
        related_name="accepted_answers",
    )

    answer = models.CharField(max_length=500)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["blank", "answer"],
                name="unique_fill_blank_answer",
            )
        ]

    def get_question_version_id(self):
        return self.blank.definition.question_version_id

class EssayDefinition(VersionContentImmutabilityMixin, models.Model):
    question_version = models.OneToOneField(
        "QuestionVersion",
        on_delete=models.CASCADE,
        related_name="essay_definition",
    )

    marking_guide = models.TextField(blank=True)

    model_answer = models.TextField(
        blank=True,
        help_text="Optional reference answer for markers. Not auto-scored.",
    )

    minimum_words = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    maximum_words = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    def clean(self):
        if (
            self.minimum_words is not None
            and self.maximum_words is not None
            and self.minimum_words > self.maximum_words
        ):
            raise ValidationError(
                "Minimum words cannot exceed maximum words."
            )

        super().clean()

    def get_question_version_id(self):
        return self.question_version_id

class MatchingDefinition(VersionContentImmutabilityMixin, models.Model):
    question_version = models.OneToOneField(
        "QuestionVersion",
        on_delete=models.CASCADE,
        related_name="matching_definition",
    )

    shuffle_right_items = models.BooleanField(default=True)

    def get_question_version_id(self):
        return self.question_version_id

class MatchingPair(VersionContentImmutabilityMixin, models.Model):
    definition = models.ForeignKey(
        MatchingDefinition,
        on_delete=models.CASCADE,
        related_name="pairs",
    )

    left_text = models.TextField()
    right_text = models.TextField()
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["definition", "order"],
                name="unique_matching_pair_order",
            )
        ]

    def get_question_version_id(self):
        return self.definition.question_version_id
