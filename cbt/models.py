from django.db import models
from django.core.exceptions import ValidationError
from decimal import Decimal 

from academic.models import Subject, GradeLevel, Topic, SubTopic, Teacher, ClassRoom
from examination.models import AssessmentSession, AssessmentComponent

class QuestionType(models.TextChoices):
    SINGLE_CHOICE = "SINGLE_CHOICE", "Single Choice"
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE", "Multiple Choice"
    TRUE_FALSE = "TRUE_FALSE", "True / False"
    SHORT_ANSWER = "SHORT_ANSWER", "Short Answer"
    NUMERIC = "NUMERIC", "Numeric"
    FILL_BLANK = "FILL_BLANK", "Fill in the Blank"
    ESSAY = "ESSAY", "Essay / Theory"
    MATCHING = "MATCHING", "Matching"


class QuestionDifficulty(models.TextChoices):
    EASY = "EASY", "Easy"
    MEDIUM = "MEDIUM", "Medium"
    HARD = "HARD", "Hard"


class QuestionStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    IN_REVIEW = "IN_REVIEW", "In Review"
    APPROVED = "APPROVED", "Approved"
    ARCHIVED = "ARCHIVED", "Archived"


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


class QuestionOption(models.Model):
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


class QuestionAttachment(models.Model):
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


class ShortAnswerDefinition(models.Model):
    question_version = models.OneToOneField(
        "QuestionVersion",
        on_delete=models.CASCADE,
        related_name="short_answer_definition",
    )

    case_sensitive = models.BooleanField(default=False)
    trim_whitespace = models.BooleanField(default=True)

    def __str__(self):
        return f"Short answer config - {self.question_version}"


class ShortAnswerVariant(models.Model):
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


class NumericAnswerDefinition(models.Model):
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


class FillBlankDefinition(models.Model):
    question_version = models.OneToOneField(
        "QuestionVersion",
        on_delete=models.CASCADE,
        related_name="fill_blank_definition",
    )

    case_sensitive = models.BooleanField(default=False)

    def __str__(self):
        return f"Fill blank config - {self.question_version}"


class FillBlankItem(models.Model):
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


class FillBlankAcceptedAnswer(models.Model):
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


class EssayDefinition(models.Model):
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


class MatchingDefinition(models.Model):
    question_version = models.OneToOneField(
        "QuestionVersion",
        on_delete=models.CASCADE,
        related_name="matching_definition",
    )

    shuffle_right_items = models.BooleanField(default=True)


class MatchingPair(models.Model):
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


class CBTExamStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    READY = "READY", "Ready"
    PUBLISHED = "PUBLISHED", "Published"
    CLOSED = "CLOSED", "Closed"


class CBTExam(models.Model):
    session = models.ForeignKey(
        AssessmentSession,
        on_delete=models.CASCADE,
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
            )
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