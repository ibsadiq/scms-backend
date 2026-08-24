from .question_bank import (
    QuestionBankViewSet,
    QuestionViewSet,
    QuestionAttachmentViewSet,
)
from .exam import (
    CBTExamViewSet,
)
from .student import (
    StudentExamViewSet,
    StudentAttemptViewSet,
    AttemptQuestionViewSet,
)
from .grading import (
    ManualGradingViewSet,
    AttemptGradeViewSet,
)

__all__ = [
    # Question Bank
    "QuestionBankViewSet",
    "QuestionViewSet",
    "QuestionAttachmentViewSet",
    # Exam
    "CBTExamViewSet",
    # Student
    "StudentExamViewSet",
    "StudentAttemptViewSet",
    "AttemptQuestionViewSet",
    # Grading
    "ManualGradingViewSet",
    "AttemptGradeViewSet",
]
