from django.db import models

from .attempt import AttemptQuestion
from .answer_definitions import (
    QuestionOption,
    FillBlankItem,
    MatchingPair,
)


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
            )
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
            )
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
        related_name="+",
    )

    selected_right_pair = models.ForeignKey(
        MatchingPair,
        on_delete=models.PROTECT,
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
        ]
