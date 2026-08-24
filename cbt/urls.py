from django.urls import path, include
from rest_framework.routers import DefaultRouter

from cbt.views import (
    QuestionBankViewSet,
    QuestionViewSet,
    QuestionAttachmentViewSet,
    CBTExamViewSet,
    StudentExamViewSet,
    StudentAttemptViewSet,
    AttemptQuestionViewSet,
    ManualGradingViewSet,
    AttemptGradeViewSet,
)

router = DefaultRouter()

# Question Bank
router.register(r"question-banks", QuestionBankViewSet, basename="question-bank")
router.register(r"questions", QuestionViewSet, basename="question")
router.register(r"question-attachments", QuestionAttachmentViewSet, basename="question-attachment")

# CBT Exam Management
router.register(r"exams", CBTExamViewSet, basename="cbt-exam")

# Student CBT Portal
router.register(r"student/exams", StudentExamViewSet, basename="student-cbt-exam")
router.register(r"student/attempts", StudentAttemptViewSet, basename="student-cbt-attempt")
router.register(r"attempt-questions", AttemptQuestionViewSet, basename="attempt-question")

# Grading & Result Posting
router.register(r"grading/manual", ManualGradingViewSet, basename="manual-grading")
router.register(r"attempt-grades", AttemptGradeViewSet, basename="attempt-grade")

urlpatterns = [
    path("", include(router.urls)),
]
