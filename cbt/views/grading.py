from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import ValidationError as DjangoValidationError, PermissionDenied
from django.shortcuts import get_object_or_404

from academic.models import AllocatedSubject
from academic.services.academic_authority_service import AcademicAuthorityService
from cbt.models import (
    AttemptGrade,
    AttemptQuestion,
    QuestionType,
    QuestionGradingStatus,
    ExamAttemptStatus,
)
from cbt.serializers import (
    AttemptGradeSerializer,
    ManualEssayGradeSerializer,
    PendingEssayGradingSerializer,
    ManualEssayGradeResponseSerializer,
)
from drf_spectacular.utils import extend_schema
from cbt.permissions import (
    CanGradeCBTExam,
    CanPostCBTResult,
)
from cbt.services import (
    ManualGradingService,
    ResultPostingService,
    CBTActorService,
)


class ManualGradingViewSet(viewsets.ViewSet):
    """
    Endpoints for teacher manual grading queue and grading essay responses.
    """
    permission_classes = [IsAuthenticated, CanGradeCBTExam]

    @extend_schema(responses={200: PendingEssayGradingSerializer(many=True)})
    @action(detail=False, methods=["get"], url_path="pending")
    def pending_queue(self, request):
        user = request.user
        qs = AttemptQuestion.objects.filter(
            attempt__status=ExamAttemptStatus.SUBMITTED,
            exam_question__question_version__question__question_type=QuestionType.ESSAY,
            grade__status=QuestionGradingStatus.PENDING_MANUAL,
        ).select_related(
            "attempt__student__user",
            "attempt__cbt_exam__subject",
            "exam_question__question_version",
            "answer__text_response",
        )

        if not AcademicAuthorityService.is_school_admin(user):
            try:
                teacher = CBTActorService.resolve_teacher(user)
            except DjangoValidationError:
                teacher = None

            if not teacher:
                return Response([])

            # Scope to teacher's allocated subjects/classes
            allocated_pairs = set(
                AllocatedSubject.objects.filter(
                    teacher_name=teacher
                ).values_list("subject_id", "class_room_id")
            )

            qs = [
                aq for aq in qs
                if (aq.attempt.cbt_exam.subject_id, aq.attempt.cbt_exam.classroom_id) in allocated_pairs
            ]

        serializer = PendingEssayGradingSerializer(qs, many=True)
        return Response(serializer.data)

    @extend_schema(
        request=ManualEssayGradeSerializer,
        responses={200: ManualEssayGradeResponseSerializer},
    )
    @action(detail=True, methods=["post"], url_path="grade")
    def grade_essay(self, request, pk=None):
        attempt_question = get_object_or_404(
            AttemptQuestion.objects.select_related(
                "attempt__cbt_exam__subject",
                "attempt__cbt_exam__classroom",
            ),
            pk=pk,
        )
        self.check_object_permissions(request, attempt_question)

        serializer = ManualEssayGradeSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        try:
            grade = serializer.grade(attempt_question)
            return Response(
                {
                    "detail": "Essay graded successfully.",
                    "awarded_marks": str(grade.awarded_marks),
                    "status": grade.status,
                },
                status=status.HTTP_200_OK,
            )
        except (DjangoValidationError, PermissionDenied) as exc:
            msg = getattr(exc, "message_dict", None) or getattr(exc, "messages", str(exc))
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)


class AttemptGradeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing attempt grades and posting results to AssessmentEntry.
    """
    queryset = AttemptGrade.objects.all().select_related(
        "attempt__student__user",
        "attempt__cbt_exam__subject",
        "attempt__cbt_exam__classroom",
    )
    serializer_class = AttemptGradeSerializer
    permission_classes = [IsAuthenticated, CanGradeCBTExam]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        exam_id = self.request.query_params.get("exam")
        if exam_id:
            qs = qs.filter(attempt__cbt_exam_id=exam_id)

        if not AcademicAuthorityService.is_school_admin(user):
            try:
                teacher = CBTActorService.resolve_teacher(user)
            except DjangoValidationError:
                teacher = None

            if not teacher:
                return AttemptGrade.objects.none()

            allocated_pairs = set(
                AllocatedSubject.objects.filter(
                    teacher_name=teacher
                ).values_list("subject_id", "class_room_id")
            )

            authorized_ids = [
                ag.id for ag in qs
                if (ag.attempt.cbt_exam.subject_id, ag.attempt.cbt_exam.classroom_id) in allocated_pairs
            ]
            qs = qs.filter(id__in=authorized_ids)

        return qs

    @action(
        detail=True,
        methods=["post"],
        url_path="post-result",
        permission_classes=[IsAuthenticated, CanPostCBTResult],
    )
    def post_result(self, request, pk=None):
        attempt_grade = self.get_object()
        try:
            entry = ResultPostingService.post(
                attempt_grade=attempt_grade,
                posted_by=request.user,
            )
            serializer = AttemptGradeSerializer(attempt_grade, context={"request": request})
            return Response(
                {
                    "detail": "CBT Result successfully posted to Assessment Entry.",
                    "grade": serializer.data,
                    "assessment_entry_id": entry.id if entry else None,
                },
                status=status.HTTP_200_OK,
            )
        except (DjangoValidationError, PermissionDenied) as exc:
            msg = getattr(exc, "message_dict", None) or getattr(exc, "messages", str(exc))
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)
