from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from ..models import AssessmentSession, AssessmentEntry, MarkedScript
from ..serializers.assessments import AssessmentSessionSerializer, AssessmentEntrySerializer, MarkedScriptSerializer
from ..permissions import CanEnterScores, CanUploadMarkedScript, CanViewMarkedScript
from ..services.assessment_service import AssessmentService


class AssessmentSessionViewSet(viewsets.ModelViewSet):
    serializer_class = AssessmentSessionSerializer
    queryset = AssessmentSession.objects.prefetch_related("classrooms")

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [CanEnterScores()]
        return super().get_permissions()

    def perform_create(self, serializer):
        # Allow admins to create without teacher profile
        if self.request.user.is_admin:
            serializer.save(created_by=None)
        else:
            serializer.save(created_by=self.request.user.teacher)


class AssessmentEntryViewSet(viewsets.ModelViewSet):
    serializer_class = AssessmentEntrySerializer
    permission_classes = [CanEnterScores]
    queryset = AssessmentEntry.objects.select_related("component", "student", "subject", "entered_by")

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        if user.is_admin:
            return qs
        if hasattr(user, "teacher"):
            return qs.filter(entered_by=user.teacher)
        return qs.none()

    def perform_create(self, serializer):
        # Allow admins to create without teacher profile
        if self.request.user.is_admin:
            serializer.save(entered_by=None)
        else:
            serializer.save(entered_by=self.request.user.teacher)

    @action(detail=False, methods=["post"], url_path="bulk-upload")
    def bulk_upload(self, request):
        try:
            # Allow admins to bulk upload without teacher profile
            teacher = getattr(request.user, "teacher", None) if not request.user.is_admin else None
            entries = AssessmentService.bulk_record_scores(
                entries=request.data.get("entries", []),
                teacher=teacher,
            )
        except DjangoValidationError as e:
            return Response(e.message_dict if hasattr(e, "message_dict") else {"detail": str(e)},
                             status=status.HTTP_400_BAD_REQUEST)
        return Response(
            AssessmentEntrySerializer(entries, many=True).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="bulk-update")
    def bulk_update(self, request):
        # Same underlying service — update_or_create makes create/update the same path
        return self.bulk_upload(request)


class MarkedScriptViewSet(viewsets.ModelViewSet):
    serializer_class = MarkedScriptSerializer
    queryset = MarkedScript.objects.select_related("student", "subject", "exam", "uploaded_by")

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [CanUploadMarkedScript()]
        return super().get_permissions()  # list/retrieve rely on get_queryset() scoping above

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

        if user.is_admin:
            return qs
        if hasattr(user, "teacher"):
            return qs.filter(uploaded_by=user.teacher)
        if user.is_student and user.active_role == "student" and hasattr(user, "student_profile"):
            return qs.filter(student=user.student_profile, visible_to_student=True)
        if user.is_parent and user.active_role == "parent" and hasattr(user, "parent"):
            return qs.filter(student__parent_guardian=user.parent, visible_to_parent=True)
        return qs.none()

    def perform_create(self, serializer):
        teacher = getattr(self.request.user, "teacher", None)
        serializer.save(uploaded_by=teacher)