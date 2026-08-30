from django.core.exceptions import ValidationError as DjangoValidationError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers as drf_serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from academic.models import (LessonDelivery, LessonPlan, LessonPlanMaterial,
    LessonPlanStatus, SchemeOfWork, SchemeOfWorkItem, SchemeOfWorkStatus)
from academic.permissions import IsAcademicPlanningUser
from academic.serializers.scheme_and_lesson import (LessonDeliverySerializer,
    LessonPlanMaterialSerializer, LessonPlanSerializer, RejectionSerializer,
    PublishedSchemeAdoptionSerializer, LessonPlanFromSchemeItemSerializer,
    CurriculumResourceMaterialSerializer, SchemeOfWorkItemSerializer,
    SchemeOfWorkSerializer)
from academic.serializers.curriculum import CurriculumResourceSerializer
from academic.services.academic_authority_service import AcademicAuthorityService
from academic.services.academic_planning_access_service import AcademicPlanningAccessService
from academic.services.lesson_delivery_service import LessonDeliveryService
from academic.services.lesson_material_service import LessonPlanMaterialService
from academic.services.lesson_plan_service import LessonPlanService
from academic.services.scheme_of_work_service import SchemeOfWorkService
from academic.services.published_scheme_adoption_service import PublishedSchemeAdoptionService


def _detail(exc):
    return list(exc)[0] if hasattr(exc, "__iter__") and not isinstance(exc, dict) else str(exc)


def _require_scheme_manager(actor, scheme):
    if not AcademicPlanningAccessService.can_manage_scheme(actor, scheme):
        raise PermissionDenied("You cannot modify another teacher's scheme of work.")


def _require_plan_manager(actor, plan):
    if not AcademicPlanningAccessService.can_manage_plan(actor, plan):
        raise PermissionDenied("You cannot modify another teacher's lesson plan.")


class SchemeOfWorkViewSet(viewsets.ModelViewSet):
    serializer_class = SchemeOfWorkSerializer
    permission_classes = [IsAcademicPlanningUser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["academic_year", "term", "curriculum_subject", "status", "created_by", "responsible_teacher"]

    def get_queryset(self):
        return SchemeOfWork.objects.select_related(
            "academic_year", "term", "curriculum_subject__subject",
            "curriculum_subject__curriculum", "curriculum_subject__grade_level",
            "created_by", "responsible_teacher", "reviewed_by",
        ).prefetch_related(
            "items__subtopics", "items__learning_objectives",
            "items__published_scheme_entry__published_scheme",
        ).filter(AcademicPlanningAccessService.scheme_scope(self.request.user)).distinct().order_by("id")

    def perform_create(self, serializer):
        teacher = AcademicAuthorityService.get_teacher(self.request.user)
        if not AcademicAuthorityService.is_school_admin(self.request.user) and not teacher:
            raise PermissionDenied("A teacher profile is required to create a scheme of work.")
        serializer.save(
            created_by=self.request.user,
            responsible_teacher=None if AcademicAuthorityService.is_school_admin(self.request.user) else teacher,
        )

    def perform_update(self, serializer):
        scheme = self.get_object()
        _require_scheme_manager(self.request.user, scheme)
        if scheme.status != SchemeOfWorkStatus.DRAFT:
            raise drf_serializers.ValidationError("Only draft schemes of work can be edited.")
        serializer.save()

    def perform_destroy(self, instance):
        _require_scheme_manager(self.request.user, instance)
        if instance.status != SchemeOfWorkStatus.DRAFT:
            raise drf_serializers.ValidationError("Only draft schemes of work can be deleted.")
        instance.delete()

    def _transition(self, callback):
        try:
            callback()
            return Response(self.get_serializer(self.get_object()).data)
        except DjangoValidationError as exc:
            return Response({"detail": _detail(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        scheme = self.get_object()
        _require_scheme_manager(request.user, scheme)
        return self._transition(lambda: SchemeOfWorkService.submit(scheme, actor=request.user))

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        scheme = self.get_object()
        return self._transition(lambda: SchemeOfWorkService.approve(scheme, actor=request.user))

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        scheme = self.get_object()
        data = RejectionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return self._transition(lambda: SchemeOfWorkService.reject(
            scheme, actor=request.user, reason=data.validated_data["reason"]))

    @action(detail=True, methods=["post"], url_path="reopen-for-revision")
    def reopen_for_revision(self, request, pk=None):
        scheme = self.get_object()
        _require_scheme_manager(request.user, scheme)
        return self._transition(lambda: SchemeOfWorkService.reopen_for_revision(scheme))

    @action(detail=False, methods=["post"], url_path="adopt-published")
    def adopt_published(self, request):
        payload = PublishedSchemeAdoptionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            scheme, created, skipped = PublishedSchemeAdoptionService.adopt(
                published_scheme=payload.validated_data["published_scheme"],
                academic_year=payload.validated_data["academic_year"],
                term=payload.validated_data["term"],
                actor=request.user,
            )
        except DjangoValidationError as exc:
            return Response({"detail": _detail(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"scheme": self.get_serializer(scheme).data, "created_items": created, "skipped_items": skipped},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="adoption-capability")
    def adoption_capability(self, request):
        payload = PublishedSchemeAdoptionSerializer(data=request.query_params)
        payload.is_valid(raise_exception=True)
        return Response(PublishedSchemeAdoptionService.capability(
            actor=request.user,
            published_scheme=payload.validated_data["published_scheme"],
            academic_year=payload.validated_data["academic_year"],
            term=payload.validated_data["term"],
        ))


class SchemeOfWorkItemViewSet(viewsets.ModelViewSet):
    serializer_class = SchemeOfWorkItemSerializer
    permission_classes = [IsAcademicPlanningUser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["scheme", "week_start", "week_end", "entry_type", "published_scheme_entry"]

    def get_queryset(self):
        schemes = SchemeOfWork.objects.filter(AcademicPlanningAccessService.scheme_scope(self.request.user))
        return SchemeOfWorkItem.objects.select_related(
            "scheme", "curriculum_topic__topic",
            "published_scheme_entry__published_scheme",
        ).prefetch_related("subtopics", "learning_objectives").filter(scheme__in=schemes).distinct()

    def _require_mutable(self, scheme):
        _require_scheme_manager(self.request.user, scheme)
        if scheme.status != SchemeOfWorkStatus.DRAFT:
            raise drf_serializers.ValidationError("Scheme items can only be changed while the scheme is draft.")

    def perform_create(self, serializer):
        self._require_mutable(serializer.validated_data["scheme"])
        serializer.save()

    def perform_update(self, serializer):
        self._require_mutable(self.get_object().scheme)
        new_scheme = serializer.validated_data.get("scheme")
        if new_scheme:
            self._require_mutable(new_scheme)
        serializer.save()

    def perform_destroy(self, instance):
        self._require_mutable(instance.scheme)
        instance.delete()


class LessonPlanViewSet(viewsets.ModelViewSet):
    serializer_class = LessonPlanSerializer
    permission_classes = [IsAcademicPlanningUser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["scheme_item", "scheme_item__scheme", "allocation", "status", "lesson_date"]

    def get_queryset(self):
        return LessonPlan.objects.select_related(
            "scheme_item__scheme__curriculum_subject", "scheme_item__curriculum_topic__topic",
            "scheme_item__published_scheme_entry__published_scheme",
            "allocation__teacher_name", "allocation__subject",
            "allocation__class_room__grade_level", "reviewed_by",
        ).prefetch_related(
            "learning_objectives", "subtopics", "materials",
            "scheme_item__learning_objectives", "scheme_item__subtopics",
        ).filter(AcademicPlanningAccessService.lesson_plan_scope(self.request.user)).distinct()

    @action(detail=False, methods=["post"], url_path="create-from-scheme-item")
    def create_from_scheme_item(self, request):
        payload = LessonPlanFromSchemeItemSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        item = payload.validated_data["scheme_item"]
        allocation = payload.validated_data["allocation"]
        if not SchemeOfWork.objects.filter(
            pk=item.scheme_id,
        ).filter(AcademicPlanningAccessService.scheme_scope(request.user)).exists():
            raise PermissionDenied("You cannot plan from this scheme of work entry.")
        if not AcademicPlanningAccessService.can_use_allocation(request.user, allocation):
            raise PermissionDenied("You cannot create a lesson plan for another teacher's allocation.")
        try:
            plan = LessonPlanService.create_from_scheme_item(
                scheme_item=item,
                allocation=allocation,
                lesson_date=payload.validated_data["lesson_date"],
                duration_minutes=payload.validated_data.get("duration_minutes"),
            )
        except DjangoValidationError as exc:
            return Response({"detail": _detail(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(plan).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="curriculum-resources")
    def curriculum_resources(self, request, pk=None):
        resources = LessonPlanMaterialService.relevant_curriculum_resources(self.get_object())
        return Response(CurriculumResourceSerializer(resources, many=True).data)

    @action(detail=True, methods=["post"], url_path="add-curriculum-resource")
    def add_curriculum_resource(self, request, pk=None):
        plan = self.get_object()
        _require_plan_manager(request.user, plan)
        payload = CurriculumResourceMaterialSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            material = LessonPlanMaterialService.add_curriculum_resource(
                lesson_plan=plan,
                resource=payload.validated_data["curriculum_resource"],
            )
        except DjangoValidationError as exc:
            return Response({"detail": _detail(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(LessonPlanMaterialSerializer(material).data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        allocation = serializer.validated_data["allocation"]
        if not AcademicPlanningAccessService.can_use_allocation(self.request.user, allocation):
            raise PermissionDenied("You cannot create a lesson plan for another teacher's allocation.")
        serializer.save()

    def perform_update(self, serializer):
        plan = self.get_object()
        _require_plan_manager(self.request.user, plan)
        if plan.status != LessonPlanStatus.DRAFT:
            raise drf_serializers.ValidationError("Only draft lesson plans can be edited.")
        allocation = serializer.validated_data.get("allocation", plan.allocation)
        if not AcademicPlanningAccessService.can_use_allocation(self.request.user, allocation):
            raise PermissionDenied("You cannot move a lesson plan to another teacher's allocation.")
        serializer.save()

    def perform_destroy(self, instance):
        _require_plan_manager(self.request.user, instance)
        if instance.status != LessonPlanStatus.DRAFT:
            raise drf_serializers.ValidationError("Only draft lesson plans can be deleted.")
        instance.delete()

    def _transition(self, callback):
        try:
            callback()
            return Response(self.get_serializer(self.get_object()).data)
        except DjangoValidationError as exc:
            return Response({"detail": _detail(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        plan = self.get_object()
        _require_plan_manager(request.user, plan)
        return self._transition(lambda: LessonPlanService.submit(plan))

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        plan = self.get_object()
        return self._transition(lambda: LessonPlanService.approve(plan, reviewed_by=request.user))

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        plan = self.get_object()
        data = RejectionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return self._transition(lambda: LessonPlanService.reject(
            plan, reviewed_by=request.user, reason=data.validated_data["reason"]))

    @action(detail=True, methods=["post"], url_path="reopen-for-revision")
    def reopen_for_revision(self, request, pk=None):
        plan = self.get_object()
        _require_plan_manager(request.user, plan)
        return self._transition(lambda: LessonPlanService.reopen_for_revision(plan))


class LessonPlanMaterialViewSet(viewsets.ModelViewSet):
    serializer_class = LessonPlanMaterialSerializer
    permission_classes = [IsAcademicPlanningUser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["lesson_plan"]

    def get_queryset(self):
        plans = LessonPlan.objects.filter(AcademicPlanningAccessService.lesson_plan_scope(self.request.user))
        return LessonPlanMaterial.objects.select_related("lesson_plan__allocation").filter(lesson_plan__in=plans).distinct()

    def perform_create(self, serializer):
        _require_plan_manager(self.request.user, serializer.validated_data["lesson_plan"])
        serializer.save()

    def perform_update(self, serializer):
        material = self.get_object()
        _require_plan_manager(self.request.user, material.lesson_plan)
        new_plan = serializer.validated_data.get("lesson_plan")
        if new_plan:
            _require_plan_manager(self.request.user, new_plan)
        serializer.save()

    def perform_destroy(self, instance):
        _require_plan_manager(self.request.user, instance.lesson_plan)
        try:
            LessonPlanMaterialService.require_mutable(instance.lesson_plan)
        except DjangoValidationError as exc:
            raise drf_serializers.ValidationError(exc.messages) from exc
        instance.delete()


class LessonDeliveryViewSet(viewsets.ModelViewSet):
    serializer_class = LessonDeliverySerializer
    permission_classes = [IsAcademicPlanningUser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["lesson_plan", "status"]

    def get_queryset(self):
        plans = LessonPlan.objects.filter(AcademicPlanningAccessService.lesson_plan_scope(self.request.user))
        return LessonDelivery.objects.select_related("lesson_plan__allocation__teacher_name", "recorded_by").filter(lesson_plan__in=plans).distinct().order_by("id")

    def _recorder(self, plan):
        _require_plan_manager(self.request.user, plan)
        teacher = AcademicAuthorityService.get_teacher(self.request.user)
        try:
            LessonDeliveryService.validate_recorder(lesson_plan=plan, recorded_by=teacher)
        except DjangoValidationError as exc:
            raise drf_serializers.ValidationError(exc.messages) from exc
        return teacher

    def perform_create(self, serializer):
        plan = serializer.validated_data["lesson_plan"]
        serializer.save(recorded_by=self._recorder(plan))

    def perform_update(self, serializer):
        delivery = self.get_object()
        plan = serializer.validated_data.get("lesson_plan", delivery.lesson_plan)
        serializer.save(recorded_by=self._recorder(plan))

    def perform_destroy(self, instance):
        self._recorder(instance.lesson_plan)
        instance.delete()
