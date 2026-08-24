from django.db import models


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

class CBTExamStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    READY = "READY", "Ready"
    PUBLISHED = "PUBLISHED", "Published"
    CLOSED = "CLOSED", "Closed"

class ExamAttemptStatus(models.TextChoices):
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    SUBMITTED = "SUBMITTED", "Submitted"
    EXPIRED = "EXPIRED", "Expired"


class QuestionGradingStatus(models.TextChoices):
    AUTO_GRADED = "AUTO_GRADED", "Auto Graded"
    PENDING_MANUAL = "PENDING_MANUAL", "Pending Manual Grading"
    MANUALLY_GRADED = "MANUALLY_GRADED", "Manually Graded"


class GradingMethod(models.TextChoices):
    AUTO = "AUTO", "Automatic"
    MANUAL = "MANUAL", "Manual"


class AttemptGradingStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    NEEDS_MANUAL = "NEEDS_MANUAL", "Needs Manual Grading"
    GRADED = "GRADED", "Graded"
    POSTED = "POSTED", "Posted to Results"
