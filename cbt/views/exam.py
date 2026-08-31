from cbt.services import CBTActorService
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError as DRFValidationError
from django.core.exceptions import ValidationError as DjangoValidationError, PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404

from academic.models import AllocatedSubject, AcademicWorkflow
from academic.services.academic_authority_service import AcademicAuthorityService
from cbt.models import (
    CBTExam,
    CBTExamStatus,
    ExamBlueprint,
    BlueprintRule,
)
from cbt.serializers import (
    CBTExamManagementSerializer,
    CBTExamCreateSerializer,
    ExamBlueprintSerializer,
    BlueprintRuleSerializer,
)
from cbt.permissions import (
    CanManageCBTExam,
    CanPublishCBTExam,
)
from cbt.services import (
    CBTExamService,
    ExamGenerationService,
    BlueprintValidationService,
)


class CBTExamViewSet(viewsets.ModelViewSet):
    """
    Management ViewSet for CBT Exams and Blueprints.
    """
    queryset = CBTExam.objects.all().select_related(
        "session",
        "component",
        "subject",
        "classroom__grade_level",
        "created_by__user",
        "blueprint",
    ).prefetch_related(
        "blueprint__rules",
        "exam_questions__question_version__question",
    )
    permission_classes = [IsAuthenticated, CanManageCBTExam]

    def get_serializer_class(self):
        if self.action == "create":
            return CBTExamCreateSerializer
        return CBTExamManagementSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        # Scoping: non-admin teachers see exams for subjects/classes they teach, created, or lead
        if not AcademicAuthorityService.is_school_admin(user):
            try:
                teacher = CBTActorService.resolve_teacher(user)
            except DjangoValidationError:
                teacher = None
            if not teacher:
                return CBTExam.objects.none()

            allocated_pairs = set(
                AllocatedSubject.objects.filter(
                    teacher_name=teacher
                ).values_list("subject_id", "class_room_id")
            )

            # Match allocated subject/classroom OR created by teacher
            # OR leadership authority (HOD, Head Teacher)
            created_ids = list(qs.filter(created_by=teacher).values_list("id", flat=True))
            allocated_ids = [
                exam.id for exam in qs
                if (exam.subject_id, exam.classroom_id) in allocated_pairs
            ]
            from academic.models import AcademicWorkflow
            leadership_ids = [
                exam.id for exam in qs
                if AcademicAuthorityService.can_approve(
                    actor=user,
                    workflow=AcademicWorkflow.CBT_PUBLISH,
                    subject=exam.subject,
                    creator=exam.created_by,
                )
            ]
            qs = qs.filter(id__in=set(created_ids + allocated_ids + leadership_ids))

        # Query filters
        subject_id = self.request.query_params.get("subject")
        classroom_id = self.request.query_params.get("classroom")
        session_id = self.request.query_params.get("session")
        status_filter = self.request.query_params.get("status")

        if subject_id:
            qs = qs.filter(subject_id=subject_id)
        if classroom_id:
            qs = qs.filter(classroom_id=classroom_id)
        if session_id:
            qs = qs.filter(session_id=session_id)
        if status_filter:
            qs = qs.filter(status=status_filter)

        return qs

    def create(self, request, *args, **kwargs):
        serializer = CBTExamCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        exam = serializer.save()
        output_serializer = CBTExamManagementSerializer(
            exam, context={"request": request}
        )
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        try:
            exam = CBTExamService.lock_for_generic_mutation(exam=self.get_object())
        except DjangoValidationError as exc:
            raise DRFValidationError(exc.messages)
        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(exam, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        try:
            exam = CBTExamService.lock_for_generic_mutation(exam=self.get_object())
        except DjangoValidationError as exc:
            raise DRFValidationError(exc.messages)
        exam.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get", "post", "patch"])
    def blueprint(self, request, pk=None):
        exam = self.get_object()

        if request.method == "GET":
            blueprint, _ = ExamBlueprint.objects.get_or_create(cbt_exam=exam)
            serializer = ExamBlueprintSerializer(blueprint)
            return Response(serializer.data)

        # Mutations require draft status
        try:
            CBTExamService.ensure_draft(exam)
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        blueprint, _ = ExamBlueprint.objects.get_or_create(cbt_exam=exam)
        if blueprint.is_locked:
            return Response(
                {"detail": "Cannot modify a locked blueprint."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ExamBlueprintSerializer(blueprint, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="blueprint/rules")
    def add_blueprint_rule(self, request, pk=None):
        exam = self.get_object()
        try:
            CBTExamService.ensure_draft(exam)
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        blueprint, _ = ExamBlueprint.objects.get_or_create(cbt_exam=exam)
        if blueprint.is_locked:
            return Response(
                {"detail": "Cannot modify a locked blueprint."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = BlueprintRuleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(blueprint=blueprint)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=["delete"],
        url_path=r"blueprint/rules/(?P<rule_id>\d+)",
    )
    def delete_blueprint_rule(self, request, pk=None, rule_id=None):
        exam = self.get_object()
        try:
            CBTExamService.ensure_draft(exam)
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        blueprint = get_object_or_404(ExamBlueprint, cbt_exam=exam)
        if blueprint.is_locked:
            return Response(
                {"detail": "Cannot modify a locked blueprint."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rule = get_object_or_404(BlueprintRule, pk=rule_id, blueprint=blueprint)
        rule.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="validate-blueprint")
    def validate_blueprint(self, request, pk=None):
        exam = self.get_object()
        blueprint = get_object_or_404(ExamBlueprint, cbt_exam=exam)
        try:
            is_valid = BlueprintValidationService.validate(blueprint=blueprint)
            return Response({"valid": is_valid, "detail": "Blueprint is valid."})
        except DjangoValidationError as exc:
            msg = getattr(exc, "message_dict", None) or getattr(exc, "messages", str(exc))
            return Response({"valid": False, "detail": msg}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def generate(self, request, pk=None):
        exam = self.get_object()
        blueprint = get_object_or_404(ExamBlueprint, cbt_exam=exam)
        try:
            ExamGenerationService.generate(blueprint=blueprint)
            exam.refresh_from_db()
            serializer = CBTExamManagementSerializer(exam, context={"request": request})
            return Response(
                {
                    "detail": "CBT Exam questions successfully generated.",
                    "exam": serializer.data,
                },
                status=status.HTTP_200_OK,
            )
        except DjangoValidationError as exc:
            msg = getattr(exc, "message_dict", None) or getattr(exc, "messages", str(exc))
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated, CanPublishCBTExam],
    )
    def publish(self, request, pk=None):
        exam = self.get_object()
        try:
            exam = CBTExamService.publish(exam=exam, actor=request.user)
            return Response(
                {"detail": "CBT Exam successfully published.", "status": exam.status}
            )
        except (DjangoValidationError, PermissionDenied) as exc:
            msg = getattr(exc, "message_dict", None) or getattr(exc, "messages", str(exc))
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated, CanPublishCBTExam],
    )
    def close(self, request, pk=None):
        exam = self.get_object()
        try:
            exam = CBTExamService.close(exam=exam)
            return Response(
                {"detail": "CBT Exam successfully closed.", "status": exam.status}
            )
        except DjangoValidationError as exc:
            msg = getattr(exc, "message_dict", None) or getattr(exc, "messages", str(exc))
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="reset-to-draft")
    def reset_to_draft(self, request, pk=None):
        exam = self.get_object()
        try:
            exam = CBTExamService.reset_to_draft(exam=exam)
            return Response(
                {"detail": "CBT Exam reset to draft successfully.", "status": exam.status}
            )
        except DjangoValidationError as exc:
            msg = getattr(exc, "message_dict", None) or getattr(exc, "messages", str(exc))
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"], url_path="approval-inbox")
    def approval_inbox(self, request):
        """
        Inbox of READY exams awaiting publishing within the actor's authority.
        """
        user = request.user
        qs = CBTExam.objects.filter(status=CBTExamStatus.READY).select_related(
            "session", "component", "subject", "classroom__grade_level", "created_by__user"
        )

        if not AcademicAuthorityService.is_school_admin(user):
            teacher = getattr(user, "teacher", None)
            if not teacher:
                return Response([])

            authorized_ids = []
            for exam in qs:
                section = None
                if exam.classroom and exam.classroom.grade_level:
                    section = exam.classroom.grade_level.section
                academic_year = None
                if exam.session and hasattr(exam.session, "academic_year"):
                    academic_year = exam.session.academic_year

                if AcademicAuthorityService.can_approve(
                    actor=user,
                    workflow=AcademicWorkflow.CBT_PUBLISH,
                    subject=exam.subject,
                    section=section,
                    academic_year=academic_year,
                    creator=exam.created_by,
                ):
                    authorized_ids.append(exam.id)

            qs = qs.filter(id__in=authorized_ids)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = CBTExamManagementSerializer(page, many=True, context={"request": request})
            return self.get_paginated_response(serializer.data)

        serializer = CBTExamManagementSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)
