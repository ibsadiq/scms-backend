from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import ValidationError as DjangoValidationError, PermissionDenied
from django.shortcuts import get_object_or_404

from academic.models import Subject, LearningObjective, AcademicWorkflow
from academic.services.academic_authority_service import AcademicAuthorityService
from cbt.models import (
    QuestionBank,
    Question,
    QuestionAttachment,
    QuestionStatus,
)
from cbt.serializers import (
    QuestionBankSerializer,
    QuestionListSerializer,
    QuestionDetailSerializer,
    QuestionCreateSerializer,
    QuestionNewVersionSerializer,
    QuestionVersionSerializer,
    QuestionAttachmentSerializer,
)
from cbt.permissions import (
    CanManageQuestionBank,
    CanReviewQuestion,
)
from cbt.services import QuestionBankService


class QuestionBankViewSet(viewsets.ModelViewSet):
    """
    CRUD endpoints for Question Banks.
    """
    queryset = QuestionBank.objects.filter(is_active=True).select_related("subject", "created_by__user")
    serializer_class = QuestionBankSerializer
    permission_classes = [IsAuthenticated, CanManageQuestionBank]

    def get_queryset(self):
        qs = super().get_queryset()
        subject_id = self.request.query_params.get("subject")
        if subject_id:
            qs = qs.filter(subject_id=subject_id)
        return qs


class QuestionViewSet(viewsets.ModelViewSet):
    """
    Question management ViewSet backed by QuestionBankService.
    """
    queryset = Question.objects.filter(is_active=True).select_related(
        "bank",
        "subject",
        "topic",
        "subtopic",
        "current_version",
        "created_by__user",
    ).prefetch_related(
        "grade_levels",
        "current_version__options",
    )
    permission_classes = [IsAuthenticated, CanManageQuestionBank]

    def get_serializer_class(self):
        if self.action == "create":
            return QuestionCreateSerializer
        elif self.action in {"retrieve", "update", "partial_update"}:
            return QuestionDetailSerializer
        return QuestionListSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        # Filters
        subject_id = self.request.query_params.get("subject")
        topic_id = self.request.query_params.get("topic")
        subtopic_id = self.request.query_params.get("subtopic")
        status_filter = self.request.query_params.get("status")
        question_type = self.request.query_params.get("question_type")
        difficulty = self.request.query_params.get("difficulty")
        grade_level_id = self.request.query_params.get("grade_level")

        if subject_id:
            qs = qs.filter(subject_id=subject_id)
        if topic_id:
            qs = qs.filter(topic_id=topic_id)
        if subtopic_id:
            qs = qs.filter(subtopic_id=subtopic_id)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if question_type:
            qs = qs.filter(question_type=question_type)
        if difficulty:
            qs = qs.filter(difficulty=difficulty)
        if grade_level_id:
            qs = qs.filter(grade_levels__id=grade_level_id)

        return qs

    def create(self, request, *args, **kwargs):
        serializer = QuestionCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        question = serializer.save()
        output_serializer = QuestionDetailSerializer(
            question, context={"request": request}
        )
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="submit-review")
    def submit_for_review(self, request, pk=None):
        question = self.get_object()
        try:
            QuestionBankService.submit_for_review(question, user=request.user)
            return Response(
                {"detail": "Question submitted for review successfully.", "status": question.status}
            )
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.message_dict if hasattr(exc, "message_dict") else exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated, CanReviewQuestion],
    )
    def approve(self, request, pk=None):
        question = self.get_object()
        comments = request.data.get("comments", "")
        try:
            QuestionBankService.approve_question(
                question=question,
                user=request.user,
                comments=comments,
            )
            return Response(
                {"detail": "Question approved successfully.", "status": question.status}
            )
        except (DjangoValidationError, PermissionDenied) as exc:
            msg = getattr(exc, "message_dict", None) or getattr(exc, "messages", str(exc))
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated, CanReviewQuestion],
    )
    def reject(self, request, pk=None):
        question = self.get_object()
        comments = request.data.get("comments", "")
        try:
            QuestionBankService.reject_question(
                question=question,
                user=request.user,
                comments=comments,
            )
            return Response(
                {"detail": "Question rejected and returned to draft.", "status": question.status}
            )
        except (DjangoValidationError, PermissionDenied) as exc:
            msg = getattr(exc, "message_dict", None) or getattr(exc, "messages", str(exc))
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="new-version")
    def new_version(self, request, pk=None):
        question = self.get_object()
        serializer = QuestionNewVersionSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        version = serializer.save_version(question)
        output_serializer = QuestionVersionSerializer(
            version, context={"request": request}
        )
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="learning-objectives")
    def align_objective(self, request, pk=None):
        question = self.get_object()
        objective_id = request.data.get("learning_objective")
        is_primary = bool(request.data.get("is_primary", False))

        objective = get_object_or_404(LearningObjective, pk=objective_id)
        try:
            alignment = QuestionBankService.align_learning_objective(
                version=question.current_version,
                learning_objective=objective,
                is_primary=is_primary,
            )
            return Response(
                {
                    "detail": "Learning objective aligned successfully.",
                    "alignment_id": alignment.id,
                },
                status=status.HTTP_201_CREATED,
            )
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.message_dict if hasattr(exc, "message_dict") else exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(
        detail=True,
        methods=["delete"],
        url_path=r"learning-objectives/(?P<objective_id>\d+)",
    )
    def remove_objective(self, request, pk=None, objective_id=None):
        question = self.get_object()
        objective = get_object_or_404(LearningObjective, pk=objective_id)
        try:
            QuestionBankService.remove_learning_objective(
                version=question.current_version,
                learning_objective=objective,
            )
            return Response(
                {"detail": "Learning objective removed successfully."},
                status=status.HTTP_204_NO_CONTENT,
            )
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.message_dict if hasattr(exc, "message_dict") else exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=["get"], url_path="review-inbox")
    def review_inbox(self, request):
        """
        Inbox of questions awaiting review within the reviewer's scope.
        """
        user = request.user
        qs = Question.objects.filter(status=QuestionStatus.IN_REVIEW, is_active=True).select_related(
            "bank", "subject", "topic", "current_version", "created_by__user"
        )

        if not AcademicAuthorityService.is_school_admin(user):
            teacher = getattr(user, "teacher", None)
            if not teacher:
                return Response([])

            # Filter questions where the teacher has review authority
            authorized_ids = [
                q.id
                for q in qs
                if AcademicAuthorityService.can_approve(
                    actor=user,
                    workflow=AcademicWorkflow.QUESTION_BANK,
                    subject=q.subject,
                    creator=q.created_by,
                )
            ]
            qs = qs.filter(id__in=authorized_ids)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = QuestionListSerializer(page, many=True, context={"request": request})
            return self.get_paginated_response(serializer.data)

        serializer = QuestionListSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)


class QuestionAttachmentViewSet(viewsets.ModelViewSet):
    queryset = QuestionAttachment.objects.all().select_related("question_version")
    serializer_class = QuestionAttachmentSerializer
    permission_classes = [IsAuthenticated, CanManageQuestionBank]
