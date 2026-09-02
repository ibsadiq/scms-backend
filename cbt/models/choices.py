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


class AttemptExpiryPolicy(models.TextChoices):
    CAP_AT_EXAM_CLOSE = "CAP_AT_EXAM_CLOSE", "Cap at exam close"
    DURATION_ONLY = "DURATION_ONLY", "Duration only"


class AttemptGrantStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    CONSUMED = "CONSUMED", "Consumed"
    REVOKED = "REVOKED", "Revoked"


class AttemptGrantSource(models.TextChoices):
    ONLINE_START = "ONLINE_START", "Online start"
    OFFLINE_PREPARATION = "OFFLINE_PREPARATION", "Offline preparation"

class ExamAttemptStatus(models.TextChoices):
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    SUBMITTED = "SUBMITTED", "Submitted"
    EXPIRED = "EXPIRED", "Expired"


class AttemptStartSource(models.TextChoices):
    ONLINE = "ONLINE", "Online"
    OFFLINE_RECONCILED = "OFFLINE_RECONCILED", "Offline reconciled"


class AnswerEventOrigin(models.TextChoices):
    ONLINE = "ONLINE", "Online"
    OFFLINE_SYNC = "OFFLINE_SYNC", "Offline sync"


class QuestionGradingStatus(models.TextChoices):
    AUTO_GRADED = "AUTO_GRADED", "Auto Graded"
    PENDING_MANUAL = "PENDING_MANUAL", "Pending Manual Grading"
    MANUALLY_GRADED = "MANUALLY_GRADED", "Manually Graded"


class GradingMethod(models.TextChoices):
    AUTO = "AUTO", "Automatic"
    MANUAL = "MANUAL", "Manual"


class AttemptGradingStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    FAILED = "FAILED", "Grading Failed"
    NEEDS_MANUAL = "NEEDS_MANUAL", "Needs Manual Grading"
    GRADED = "GRADED", "Graded"
    POSTED = "POSTED", "Posted to Results"
