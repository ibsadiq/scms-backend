from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404

from academic.models import StudentClassEnrollment
from cbt.models import (
    CBTExam,
    CBTExamStatus,
    ExamAttempt,
    AttemptQuestion,
)
from cbt.serializers import (
    StudentAvailableExamSerializer,
    ExamAttemptSerializer,
    ExamAttemptListSerializer,
    AnswerSaveSerializer,
    FlagQuestionSerializer,
    AttemptQuestionSerializer,
)
from cbt.permissions import (
    CanTakeCBTExam,
    CanAccessOwnAttempt,
)
from cbt.services import (
    CBTActorService,
    ExamAttemptService,
    StudentAnswerService,
    AttemptGradingService,
)


class StudentExamViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Student view for listing and starting eligible published CBT exams.
    """
    serializer_class = StudentAvailableExamSerializer
    permission_classes = [IsAuthenticated, CanTakeCBTExam]

    def get_queryset(self):
        user = self.request.user
        try:
            student = CBTActorService.resolve_student(user)
        except DjangoValidationError:
            return CBTExam.objects.none()

        # Find classrooms where student is actively enrolled
        enrollments = StudentClassEnrollment.objects.filter(
            student=student,
            is_active=True,
        ).select_related("classroom", "academic_year")

        active_classroom_ids = enrollments.values_list("classroom_id", flat=True)
        active_year_ids = enrollments.values_list("academic_year_id", flat=True)

        return CBTExam.objects.filter(
            status=CBTExamStatus.PUBLISHED,
            classroom_id__in=active_classroom_ids,
            session__academic_year_id__in=active_year_ids,
        ).select_related("subject", "classroom__name", "session").prefetch_related("attempts")

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        exam = self.get_object()
        student = CBTActorService.resolve_student(request.user)

        try:
            attempt = ExamAttemptService.start_attempt(
                exam=exam,
                student=student,
            )
            serializer = ExamAttemptSerializer(attempt, context={"request": request})
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except DjangoValidationError as exc:
            msg = getattr(exc, "message_dict", None) or getattr(exc, "messages", str(exc))
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)


class StudentAttemptViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Student viewset for retrieving active/submitted attempts and submitting.
    """
    serializer_class = ExamAttemptSerializer
    permission_classes = [IsAuthenticated, CanAccessOwnAttempt]

    def get_queryset(self):
        user = self.request.user
        try:
            student = CBTActorService.resolve_student(user)
        except DjangoValidationError:
            return ExamAttempt.objects.none()

        return ExamAttempt.objects.filter(student=student).select_related(
            "cbt_exam__subject",
            "cbt_exam__classroom__name",
        ).prefetch_related(
            "attempt_questions__exam_question__question_version__question",
            "attempt_questions__option_order__question_option",
            "attempt_questions__answer",
        )

    def retrieve(self, request, *args, **kwargs):
        attempt = self.get_object()
        # Auto-refresh expired attempt
        ExamAttemptService.refresh_status(attempt=attempt)
        serializer = self.get_serializer(attempt)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        attempt = self.get_object()
        try:
            attempt = ExamAttemptService.submit(attempt=attempt)

            # Trigger automatic grading for objective questions
            try:
                AttemptGradingService.grade_attempt(attempt=attempt)
            except Exception:
                # Automatic grading failure should not block submission recording
                pass

            serializer = ExamAttemptSerializer(attempt, context={"request": request})
            return Response(
                {
                    "detail": "Exam attempt successfully submitted.",
                    "attempt": serializer.data,
                },
                status=status.HTTP_200_OK,
            )
        except DjangoValidationError as exc:
            msg = getattr(exc, "message_dict", None) or getattr(exc, "messages", str(exc))
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)


class AttemptQuestionViewSet(viewsets.GenericViewSet):
    """
    Endpoints for student answering, clearing, and flagging attempt questions.
    """
    queryset = AttemptQuestion.objects.all().select_related(
        "attempt__student",
        "exam_question__question_version__question",
    )
    permission_classes = [IsAuthenticated, CanAccessOwnAttempt]
    serializer_class = AttemptQuestionSerializer

    @action(detail=True, methods=["put", "patch", "delete"], url_path="answer")
    def answer(self, request, pk=None):
        attempt_question = self.get_object()

        if request.method == "DELETE":
            try:
                StudentAnswerService.clear_answer(attempt_question=attempt_question)
                output_serializer = AttemptQuestionSerializer(
                    attempt_question, context={"request": request}
                )
                return Response(
                    {
                        "detail": "Answer cleared successfully.",
                        "question": output_serializer.data,
                    },
                    status=status.HTTP_200_OK,
                )
            except DjangoValidationError as exc:
                msg = getattr(exc, "message_dict", None) or getattr(exc, "messages", str(exc))
                return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

        serializer = AnswerSaveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            serializer.save_answer(attempt_question)
            output_serializer = AttemptQuestionSerializer(
                attempt_question, context={"request": request}
            )
            return Response(
                {
                    "detail": "Answer saved successfully.",
                    "question": output_serializer.data,
                },
                status=status.HTTP_200_OK,
            )
        except DjangoValidationError as exc:
            msg = getattr(exc, "message_dict", None) or getattr(exc, "messages", str(exc))
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["patch"], url_path="flag")
    def flag(self, request, pk=None):
        attempt_question = self.get_object()
        serializer = FlagQuestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        serializer.save_flag(attempt_question)
        output_serializer = AttemptQuestionSerializer(
            attempt_question, context={"request": request}
        )
        return Response(
            {
                "detail": f"Question {'flagged' if attempt_question.is_flagged else 'unflagged'} successfully.",
                "question": output_serializer.data,
            },
            status=status.HTTP_200_OK,
        )
