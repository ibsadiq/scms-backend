import uuid

from django.db import models

from .attempt import AttemptQuestion
from .answer_definitions import (
    QuestionOption,
    FillBlankItem,
    MatchingPair,
)
from .publication import (
    PublishedExamChoice,
    PublishedExamBlank,
    PublishedExamMatchingItem,
)
from .choices import AnswerEventOrigin


class StudentAnswer(models.Model):
    attempt_question = models.OneToOneField(
        AttemptQuestion,
        on_delete=models.CASCADE,
        related_name="answer",
    )

    is_answered = models.BooleanField(
        default=False,
    )

    answered_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        indexes = [
            models.Index(
                fields=[
                    "is_answered",
                ]
            ),
        ]

    def __str__(self):
        return f"Answer - {self.attempt_question}"

class StudentChoiceAnswer(models.Model):
    student_answer = models.ForeignKey(
        StudentAnswer,
        on_delete=models.CASCADE,
        related_name="selected_options",
    )

    question_option = models.ForeignKey(
        QuestionOption,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="student_selections",
    )
    published_choice = models.ForeignKey(
        PublishedExamChoice,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="student_selections",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "student_answer",
                    "question_option",
                ],
                name="unique_selected_option_per_student_answer",
            ),
            models.UniqueConstraint(
                fields=["student_answer", "published_choice"],
                name="unique_published_choice_per_student_answer",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(question_option__isnull=False, published_choice__isnull=True)
                    | models.Q(question_option__isnull=True, published_choice__isnull=False)
                ),
                name="student_choice_has_one_source",
            ),
        ]

    def __str__(self):
        return (
            f"{self.student_answer} - "
            f"{self.question_option}"
        )

class StudentTextAnswer(models.Model):
    student_answer = models.OneToOneField(
        StudentAnswer,
        on_delete=models.CASCADE,
        related_name="text_response",
    )

    text = models.TextField()

    def __str__(self):
        return f"Text response - {self.student_answer}"

class StudentNumericAnswer(models.Model):
    student_answer = models.OneToOneField(
        StudentAnswer,
        on_delete=models.CASCADE,
        related_name="numeric_response",
    )

    value = models.DecimalField(
        max_digits=18,
        decimal_places=6,
    )

    def __str__(self):
        return str(self.value)

class StudentFillBlankAnswer(models.Model):
    student_answer = models.ForeignKey(
        StudentAnswer,
        on_delete=models.CASCADE,
        related_name="blank_responses",
    )

    blank = models.ForeignKey(
        FillBlankItem,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="student_answers",
    )
    published_blank = models.ForeignKey(
        PublishedExamBlank,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="student_answers",
    )

    answer = models.CharField(
        max_length=500,
    )

    class Meta:
        ordering = ["blank__position"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "student_answer",
                    "blank",
                ],
                name="unique_student_answer_per_blank",
            ),
            models.UniqueConstraint(
                fields=["student_answer", "published_blank"],
                name="unique_student_answer_per_published_blank",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(blank__isnull=False, published_blank__isnull=True)
                    | models.Q(blank__isnull=True, published_blank__isnull=False)
                ),
                name="student_blank_has_one_source",
            ),
        ]

class StudentMatchingAnswer(models.Model):
    student_answer = models.ForeignKey(
        StudentAnswer,
        on_delete=models.CASCADE,
        related_name="matching_responses",
    )

    left_pair = models.ForeignKey(
        MatchingPair,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    selected_right_pair = models.ForeignKey(
        MatchingPair,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    published_left_item = models.ForeignKey(
        PublishedExamMatchingItem,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    published_right_item = models.ForeignKey(
        PublishedExamMatchingItem,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "student_answer",
                    "left_pair",
                ],
                name="unique_match_per_left_item",
            ),
            models.UniqueConstraint(
                fields=[
                    "student_answer",
                    "selected_right_pair",
                ],
                name="unique_right_match_per_student_answer",
            ),
            models.UniqueConstraint(
                fields=["student_answer", "published_left_item"],
                name="unique_published_left_match",
            ),
            models.UniqueConstraint(
                fields=["student_answer", "published_right_item"],
                name="unique_published_right_match",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        left_pair__isnull=False,
                        selected_right_pair__isnull=False,
                        published_left_item__isnull=True,
                        published_right_item__isnull=True,
                    )
                    | models.Q(
                        left_pair__isnull=True,
                        selected_right_pair__isnull=True,
                        published_left_item__isnull=False,
                        published_right_item__isnull=False,
                    )
                ),
                name="student_match_has_one_source",
            ),
        ]


class AttemptAnswerEvent(models.Model):
    class Operation(models.TextChoices):
        SET = "SET", "Set"
        CLEAR = "CLEAR", "Clear"

    class Outcome(models.TextChoices):
        ACCEPTED = "ACCEPTED", "Accepted"
        STALE = "STALE", "Stale"

    event_id = models.UUIDField(default=uuid.uuid4)
    attempt = models.ForeignKey(
        "ExamAttempt",
        on_delete=models.PROTECT,
        related_name="answer_events",
    )
    attempt_question = models.ForeignKey(
        AttemptQuestion,
        on_delete=models.PROTECT,
        related_name="answer_events",
    )
    client_id = models.UUIDField()
    client_sequence = models.PositiveBigIntegerField()
    base_revision = models.PositiveBigIntegerField(null=True, blank=True)
    operation = models.CharField(max_length=10, choices=Operation.choices)
    payload = models.JSONField(default=dict, blank=True)
    payload_hash = models.CharField(max_length=64)
    outcome = models.CharField(max_length=12, choices=Outcome.choices)
    server_revision = models.PositiveBigIntegerField()
    client_timestamp = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    origin = models.CharField(
        max_length=16,
        choices=AnswerEventOrigin.choices,
        default=AnswerEventOrigin.ONLINE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "event_id"],
                name="unique_answer_event_per_attempt",
            ),
            models.UniqueConstraint(
                fields=["attempt_question", "client_id", "client_sequence"],
                name="unique_client_sequence_per_attempt_question",
            ),
        ]
        indexes = [
            models.Index(fields=["attempt", "server_revision"]),
            models.Index(fields=["attempt_question", "client_id", "client_sequence"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Attempt answer events are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Attempt answer events are append-only.")


class AttemptQuestionClientState(models.Model):
    attempt_question = models.ForeignKey(
        AttemptQuestion,
        on_delete=models.CASCADE,
        related_name="client_states",
    )
    client_id = models.UUIDField()
    last_client_sequence = models.PositiveBigIntegerField(default=0)
    last_server_revision = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["attempt_question", "client_id"],
                name="unique_client_state_per_attempt_question",
            )
        ]
