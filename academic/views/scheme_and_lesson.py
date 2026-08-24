from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import ValidationError
from academic.services.scheme_of_work_service import SchemeOfWorkService
from academic.services.lesson_plan_service import LessonPlanService
from academic.models.scheme_and_lesson import (
    SchemeOfWork,
    SchemeOfWorkItem,
    LessonPlan,
    LessonPlanMaterial,
)
from academic.serializers.scheme_and_lesson import (
    SchemeOfWorkSerializer,
    SchemeOfWorkItemSerializer,
    LessonPlanSerializer,
    LessonPlanMaterialSerializer,
    RejectionSerializer,
)

class SchemeOfWorkViewSet(viewsets.ModelViewSet):
    queryset = SchemeOfWork.objects.all()
    serializer_class = SchemeOfWorkSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        scheme = self.get_object()
        try:
            SchemeOfWorkService.submit(scheme, actor=request.user)
            serializer = self.get_serializer(scheme)
            return Response(serializer.data)
        except ValidationError as e:
            return Response({"detail": list(e)[0] if hasattr(e, '__iter__') and not isinstance(e, dict) else str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        scheme = self.get_object()
        try:
            SchemeOfWorkService.approve(scheme, actor=request.user)
            serializer = self.get_serializer(scheme)
            return Response(serializer.data)
        except ValidationError as e:
            return Response({"detail": list(e)[0] if hasattr(e, '__iter__') and not isinstance(e, dict) else str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        scheme = self.get_object()
        serializer = RejectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            SchemeOfWorkService.reject(scheme, actor=request.user, reason=serializer.validated_data["reason"])
            response_serializer = self.get_serializer(scheme)
            return Response(response_serializer.data)
        except ValidationError as e:
            return Response({"detail": list(e)[0] if hasattr(e, '__iter__') and not isinstance(e, dict) else str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="reopen-for-revision")
    def reopen_for_revision(self, request, pk=None):
        scheme = self.get_object()
        try:
            SchemeOfWorkService.reopen_for_revision(scheme)
            serializer = self.get_serializer(scheme)
            return Response(serializer.data)
        except ValidationError as e:
            return Response({"detail": list(e)[0] if hasattr(e, '__iter__') and not isinstance(e, dict) else str(e)}, status=status.HTTP_400_BAD_REQUEST)

class SchemeOfWorkItemViewSet(viewsets.ModelViewSet):
    queryset = SchemeOfWorkItem.objects.all()
    serializer_class = SchemeOfWorkItemSerializer
    permission_classes = [IsAuthenticated]

class LessonPlanViewSet(viewsets.ModelViewSet):
    queryset = LessonPlan.objects.all()
    serializer_class = LessonPlanSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        plan = self.get_object()
        try:
            LessonPlanService.submit(plan)
            serializer = self.get_serializer(plan)
            return Response(serializer.data)
        except ValidationError as e:
            return Response({"detail": list(e)[0] if hasattr(e, '__iter__') and not isinstance(e, dict) else str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        plan = self.get_object()
        try:
            LessonPlanService.approve(plan, reviewed_by=request.user)
            serializer = self.get_serializer(plan)
            return Response(serializer.data)
        except ValidationError as e:
            return Response({"detail": list(e)[0] if hasattr(e, '__iter__') and not isinstance(e, dict) else str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        plan = self.get_object()
        req_serializer = RejectionSerializer(data=request.data)
        req_serializer.is_valid(raise_exception=True)
        try:
            LessonPlanService.reject(plan, reviewed_by=request.user, reason=req_serializer.validated_data["reason"])
            serializer = self.get_serializer(plan)
            return Response(serializer.data)
        except ValidationError as e:
            return Response({"detail": list(e)[0] if hasattr(e, '__iter__') and not isinstance(e, dict) else str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="reopen-for-revision")
    def reopen_for_revision(self, request, pk=None):
        plan = self.get_object()
        try:
            LessonPlanService.reopen_for_revision(plan)
            serializer = self.get_serializer(plan)
            return Response(serializer.data)
        except ValidationError as e:
            return Response({"detail": list(e)[0] if hasattr(e, '__iter__') and not isinstance(e, dict) else str(e)}, status=status.HTTP_400_BAD_REQUEST)

class LessonPlanMaterialViewSet(viewsets.ModelViewSet):
    queryset = LessonPlanMaterial.objects.all()
    serializer_class = LessonPlanMaterialSerializer
    permission_classes = [IsAuthenticated]

    def perform_destroy(self, instance):
        from django.core.exceptions import ValidationError as DjangoValidationError
        from rest_framework.exceptions import ValidationError as DRFValidationError
        from academic.services.lesson_material_service import LessonPlanMaterialService

        try:
            LessonPlanMaterialService.require_mutable(instance.lesson_plan)
        except DjangoValidationError as exc:
            raise DRFValidationError(exc.messages) from exc
        instance.delete()
