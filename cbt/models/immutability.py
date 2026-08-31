from django.apps import apps
from django.core.exceptions import ValidationError


IMMUTABLE_VERSION_MESSAGE = (
    "Question versions referenced by generated CBT exams cannot be modified. "
    "Create a new question version instead."
)


def is_question_version_referenced(question_version_id):
    if not question_version_id:
        return False
    ExamQuestion = apps.get_model("cbt", "ExamQuestion")
    return ExamQuestion.objects.filter(
        question_version_id=question_version_id
    ).exists()


def ensure_question_version_mutable(question_version_id):
    if is_question_version_referenced(question_version_id):
        raise ValidationError(IMMUTABLE_VERSION_MESSAGE)


class VersionContentImmutabilityMixin:
    """Protect delivery/grading content once its version is in an exam."""

    def get_question_version_id(self):
        raise NotImplementedError

    def save(self, *args, **kwargs):
        ensure_question_version_mutable(self.get_question_version_id())
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        ensure_question_version_mutable(self.get_question_version_id())
        return super().delete(*args, **kwargs)
