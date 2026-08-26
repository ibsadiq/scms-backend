from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from academic.permissions import IsSchoolAdmin
from academic.models import Staff, Student
from idcards.models import (
    AuthorizedSignature, AuthorizedSignatureVersion, HolderType, IDCard,
    IDCardDesignAsset, IDCardTemplate, IDCardTemplateAssignment, IDCardTemplateVersion, RFIDCredential,
)
from idcards.serializers import (
    AuthorizedSignatureCreateSerializer, AuthorizedSignatureReplaceSerializer,
    AuthorizedSignatureSerializer, AuthorizedSignatureVersionSerializer,
    CardDeactivateSerializer, CardReplaceSerializer, IDCardDesignAssetSerializer,
    IDCardDesignAssetUploadSerializer, IDCardSerializer, IDCardTemplateAssignmentSerializer, IDCardTemplateSerializer,
    IDCardTemplateFieldSerializer, IDCardTemplateVersionSerializer, RFIDCredentialSerializer,
    RFIDReplaceSerializer, RFIDRevokeSerializer, TemplateDuplicateSerializer,
)
from idcards.services import (
    AuthorizedSignatureService, CardService, DynamicFieldRegistry,
    IDCardAssetService, IDCardRenderService, IDCardTemplateLifecycleService, IDCardTemplateResolver,
    RFIDCredentialService,
)
from drf_spectacular.utils import OpenApiParameter, extend_schema


class NoDestroyModelViewSet(viewsets.ModelViewSet):
    http_method_names = ("get", "post", "put", "patch", "head", "options")
    permission_classes = (IsAuthenticated, IsSchoolAdmin)


class IDCardTemplateViewSet(NoDestroyModelViewSet):
    queryset = IDCardTemplate.objects.select_related("current_draft_version", "current_published_version")
    serializer_class = IDCardTemplateSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.query_params.get("holder_type"):
            queryset = queryset.filter(holder_type=self.request.query_params["holder_type"])
        if self.request.query_params.get("is_active") is not None:
            queryset = queryset.filter(is_active=self.request.query_params["is_active"].lower() == "true")
        return queryset

    @extend_schema(request=None, responses=IDCardTemplateSerializer)
    @action(detail=True, methods=("post",))
    def activate(self, request, pk=None):
        template = self.get_object()
        if template.is_archived:
            return Response({"detail": "Archived templates cannot be activated."}, status=status.HTTP_400_BAD_REQUEST)
        if template.current_draft_version:
            try:
                IDCardTemplateLifecycleService.publish(template.current_draft_version, actor=request.user)
            except DjangoValidationError as exc:
                return Response({"detail": exc.message_dict if hasattr(exc, "message_dict") else exc.messages}, status=400)
        elif template.current_published_version:
            template.is_active = True
            template.save(update_fields=("is_active", "updated_at"))
        else:
            return Response({"detail": "Template has no publishable version."}, status=status.HTTP_400_BAD_REQUEST)
        template.refresh_from_db()
        return Response(self.get_serializer(template).data)

    @extend_schema(request=None, responses=IDCardTemplateSerializer)
    @action(detail=True, methods=("post",))
    def deactivate(self, request, pk=None):
        template = IDCardTemplateLifecycleService.archive(self.get_object())
        return Response(self.get_serializer(template).data)

    @extend_schema(request=None, responses=IDCardTemplateVersionSerializer)
    @action(detail=True, methods=("post",), url_path="create-draft")
    def create_draft(self, request, pk=None):
        try:
            version = IDCardTemplateLifecycleService.create_draft(self.get_object(), actor=request.user)
        except DjangoValidationError as exc:
            return Response({"detail": exc.message_dict if hasattr(exc, "message_dict") else exc.messages}, status=400)
        return Response(IDCardTemplateVersionSerializer(version).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=TemplateDuplicateSerializer, responses=IDCardTemplateSerializer)
    @action(detail=True, methods=("post",))
    def duplicate(self, request, pk=None):
        serializer = TemplateDuplicateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            duplicate = IDCardTemplateLifecycleService.duplicate(
                self.get_object(), name=serializer.validated_data["name"], actor=request.user,
            )
        except DjangoValidationError as exc:
            return Response({"detail": exc.message_dict if hasattr(exc, "message_dict") else exc.messages}, status=400)
        return Response(self.get_serializer(duplicate).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=IDCardTemplateSerializer)
    @action(detail=True, methods=("post",))
    def archive(self, request, pk=None):
        template = IDCardTemplateLifecycleService.archive(self.get_object())
        return Response(self.get_serializer(template).data)

    @action(detail=True, methods=("post",), url_path="preview-context")
    def preview_context(self, request, pk=None):
        template = self.get_object()
        data = {"template": template, "expires_at": request.data.get("expires_at")}
        if template.holder_type == HolderType.STUDENT:
            data["student_id"] = request.data.get("student")
        else:
            data["staff_id"] = request.data.get("staff")
        holder_model = IDCard._meta.get_field("student" if template.holder_type == HolderType.STUDENT else "staff").remote_field.model
        holder_id = data.get("student_id") or data.get("staff_id")
        try:
            holder = holder_model.objects.get(pk=holder_id)
        except (holder_model.DoesNotExist, ValueError, TypeError):
            return Response({"detail": "A valid matching holder is required."}, status=status.HTTP_400_BAD_REQUEST)
        kwargs = {"student": holder} if template.holder_type == HolderType.STUDENT else {"staff": holder}
        # Unsaved preview card: no identifier is persisted or consumed.
        card = IDCard(
            template=template, template_version=template.current_draft_version or template.current_published_version,
            card_number="PREVIEW", **kwargs,
        )
        return Response({"template": self.get_serializer(template).data, "values": CardService.prepare_card_context(card)["values"]})


class IDCardTemplateVersionViewSet(viewsets.GenericViewSet):
    queryset = IDCardTemplateVersion.objects.select_related("template", "created_from_version")
    serializer_class = IDCardTemplateVersionSerializer
    permission_classes = (IsAuthenticated, IsSchoolAdmin)
    http_method_names = ("get", "patch", "post", "head", "options")
    pagination_class = None

    def list(self, request):
        queryset = self.get_queryset()
        if request.query_params.get("template"):
            queryset = queryset.filter(template=request.query_params["template"])
        return Response(self.get_serializer(queryset, many=True).data)

    def retrieve(self, request, pk=None):
        return Response(self.get_serializer(self.get_object()).data)

    def partial_update(self, request, pk=None):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @extend_schema(request=None, responses=IDCardTemplateVersionSerializer)
    @action(detail=True, methods=("post",))
    def publish(self, request, pk=None):
        try:
            version = IDCardTemplateLifecycleService.publish(self.get_object(), actor=request.user)
        except DjangoValidationError as exc:
            return Response({"detail": exc.message_dict if hasattr(exc, "message_dict") else exc.messages}, status=400)
        return Response(self.get_serializer(version).data)

    @extend_schema(request=None, responses=IDCardTemplateVersionSerializer)
    @action(detail=True, methods=("post",))
    def archive(self, request, pk=None):
        try:
            version = IDCardTemplateLifecycleService.archive_version(self.get_object())
        except DjangoValidationError as exc:
            return Response({"detail": exc.message_dict if hasattr(exc, "message_dict") else exc.messages}, status=400)
        return Response(self.get_serializer(version).data)


class IDCardTemplateAssignmentViewSet(viewsets.ModelViewSet):
    queryset = IDCardTemplateAssignment.objects.select_related(
        "template__current_published_version", "section", "grade_level", "classroom__grade_level", "department"
    )
    serializer_class = IDCardTemplateAssignmentSerializer
    permission_classes = (IsAuthenticated, IsSchoolAdmin)

    def get_queryset(self):
        queryset = super().get_queryset()
        holder_type = self.request.query_params.get("holder_type")
        return queryset.filter(holder_type=holder_type) if holder_type else queryset

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=("is_active", "updated_at"))

    @action(detail=False, methods=("post",), url_path="resolve")
    def resolve(self, request):
        holder_type, holder_id = request.data.get("holder_type"), request.data.get("holder_id")
        model = Student if holder_type == HolderType.STUDENT else Staff if holder_type == HolderType.STAFF else None
        if not model:
            return Response({"detail": "A valid holder_type is required."}, status=400)
        try:
            holder = model.objects.get(pk=holder_id)
            result = IDCardTemplateResolver.resolve_for_holder(holder_type, holder)
        except model.DoesNotExist:
            return Response({"detail": "Holder not found."}, status=404)
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages}, status=400)
        return Response({"template": IDCardTemplateSerializer(result.template).data,
                         "template_version": IDCardTemplateVersionSerializer(result.template_version).data,
                         "matched_scope": result.matched_scope,
                         "assignment": self.get_serializer(result.assignment).data, "path": result.path})


class IDCardViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = IDCard.objects.select_related(
        "student__classroom__grade_level", "student__classroom__stream",
        "staff__user", "staff__department", "template", "template_version", "issued_by",
    ).prefetch_related("rfid_credentials")
    serializer_class = IDCardSerializer
    permission_classes = (IsAuthenticated, IsSchoolAdmin)

    def get_queryset(self):
        queryset = super().get_queryset()
        for field in ("student", "staff", "template", "status"):
            value = self.request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})
        holder_type = self.request.query_params.get("holder_type")
        if holder_type == HolderType.STUDENT:
            queryset = queryset.filter(student__isnull=False)
        elif holder_type == HolderType.STAFF:
            queryset = queryset.filter(staff__isnull=False)
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            card = serializer.save()
        except DjangoValidationError as exc:
            return Response({"detail": exc.message_dict if hasattr(exc, "message_dict") else exc.messages}, status=400)
        return Response(self.get_serializer(card).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("post",))
    def deactivate(self, request, pk=None):
        serializer = CardDeactivateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            card = CardService.deactivate_card(self.get_object(), **serializer.validated_data)
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(card).data)

    @action(detail=True, methods=("post",))
    def replace(self, request, pk=None):
        serializer = CardReplaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            card = CardService.replace_card(
                self.get_object(), actor=request.user, **serializer.validated_data
            )
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.message_dict if hasattr(exc, "message_dict") else exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(self.get_serializer(card).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("get",), url_path="preview-context")
    def preview_context(self, request, pk=None):
        context = CardService.prepare_card_context(self.get_object())
        return Response({"template": IDCardTemplateSerializer(context["template"]).data, "values": context["values"]})

    @action(detail=True, methods=("get",), url_path="preview")
    def preview(self, request, pk=None):
        card = self.get_object()
        data = IDCardRenderService.get_preview_data(card)
        return Response(data)

    @action(detail=True, methods=("get",), url_path="print")
    def print_card(self, request, pk=None):
        card = self.get_object()
        pdf_bytes = IDCardRenderService.generate_pdf(card)
        download = request.query_params.get("download", "").lower() in ("true", "1", "yes")
        disposition = "attachment" if download else "inline"
        filename = f"id-card-{card.card_number}.pdf"
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return response


@extend_schema(
    parameters=[OpenApiParameter("holder_type", str, required=True)],
    responses={200: IDCardTemplateFieldSerializer(many=True)},
)
@api_view(("GET",))
@permission_classes((IsAuthenticated, IsSchoolAdmin))
def template_fields(request):
    holder_type = request.query_params.get("holder_type")
    try:
        fields = DynamicFieldRegistry.available(holder_type)
    except DjangoValidationError as exc:
        return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
    return Response(fields)


class RFIDCredentialViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = RFIDCredential.objects.select_related("id_card", "revoked_by")
    serializer_class = RFIDCredentialSerializer
    permission_classes = (IsAuthenticated, IsSchoolAdmin)

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.query_params.get("id_card"):
            queryset = queryset.filter(id_card=self.request.query_params["id_card"])
        if self.request.query_params.get("status"):
            queryset = queryset.filter(status=self.request.query_params["status"])
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            credential = serializer.save()
        except DjangoValidationError as exc:
            return Response({"detail": exc.message_dict if hasattr(exc, "message_dict") else exc.messages}, status=400)
        return Response(self.get_serializer(credential).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("post",))
    def revoke(self, request, pk=None):
        serializer = RFIDRevokeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            credential = RFIDCredentialService.revoke(self.get_object(), actor=request.user, **serializer.validated_data)
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages}, status=400)
        return Response(self.get_serializer(credential).data)

    @action(detail=True, methods=("post",))
    def replace(self, request, pk=None):
        serializer = RFIDReplaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            credential = RFIDCredentialService.replace(self.get_object(), new_uid=serializer.validated_data["uid"], actor=request.user, reason=serializer.validated_data["reason"])
        except DjangoValidationError as exc:
            return Response({"detail": exc.message_dict if hasattr(exc, "message_dict") else exc.messages}, status=400)
        return Response(self.get_serializer(credential).data, status=status.HTTP_201_CREATED)


class IDCardDesignAssetViewSet(viewsets.ModelViewSet):
    queryset = IDCardDesignAsset.objects.all()
    serializer_class = IDCardDesignAssetSerializer
    permission_classes = (IsAuthenticated, IsSchoolAdmin)

    def get_queryset(self):
        queryset = super().get_queryset()
        asset_type = self.request.query_params.get("asset_type")
        if asset_type:
            queryset = queryset.filter(asset_type=asset_type)
        if self.request.query_params.get("all", "").lower() != "true":
            queryset = queryset.filter(is_active=True)
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = IDCardDesignAssetUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            asset = IDCardAssetService.create_asset(
                file=serializer.validated_data["file"],
                name=serializer.validated_data.get("name") or serializer.validated_data["file"].name,
                asset_type=serializer.validated_data.get("asset_type", IDCardDesignAsset.AssetType.IMAGE),
                user=request.user,
            )
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.message_dict if hasattr(exc, "message_dict") else exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(IDCardDesignAssetSerializer(asset).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        asset = self.get_object()
        try:
            IDCardAssetService.delete_asset(asset)
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.messages if hasattr(exc, "messages") else str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=("post",))
    def archive(self, request, pk=None):
        asset = IDCardAssetService.archive_asset(self.get_object())
        return Response(self.get_serializer(asset).data)


class AuthorizedSignatureViewSet(viewsets.ModelViewSet):
    queryset = AuthorizedSignature.objects.select_related("current_version").prefetch_related("versions")
    serializer_class = AuthorizedSignatureSerializer
    permission_classes = (IsAuthenticated, IsSchoolAdmin)

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.query_params.get("all", "").lower() != "true":
            queryset = queryset.filter(is_active=True)
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = AuthorizedSignatureCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            signature = AuthorizedSignatureService.create_signature(
                name=serializer.validated_data["name"],
                signatory_name=serializer.validated_data["signatory_name"],
                signatory_title=serializer.validated_data["signatory_title"],
                description=serializer.validated_data.get("description", ""),
                file=serializer.validated_data["image"],
                user=request.user,
            )
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.message_dict if hasattr(exc, "message_dict") else exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(AuthorizedSignatureSerializer(signature).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        signature = self.get_object()
        try:
            AuthorizedSignatureService.delete_signature(signature)
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.messages if hasattr(exc, "messages") else str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=("post",))
    def replace(self, request, pk=None):
        signature = self.get_object()
        serializer = AuthorizedSignatureReplaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            new_version = AuthorizedSignatureService.replace_signature_image(
                signature,
                file=serializer.validated_data["image"],
                user=request.user,
            )
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.message_dict if hasattr(exc, "message_dict") else exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(AuthorizedSignatureVersionSerializer(new_version).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("post",))
    def activate(self, request, pk=None):
        signature = AuthorizedSignatureService.activate_signature(self.get_object())
        return Response(self.get_serializer(signature).data)

    @action(detail=True, methods=("post",))
    def deactivate(self, request, pk=None):
        signature = AuthorizedSignatureService.deactivate_signature(self.get_object())
        return Response(self.get_serializer(signature).data)


class AuthorizedSignatureVersionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuthorizedSignatureVersion.objects.select_related("signature")
    serializer_class = AuthorizedSignatureVersionSerializer
    permission_classes = (IsAuthenticated, IsSchoolAdmin)

    def get_queryset(self):
        queryset = super().get_queryset()
        signature_id = self.request.query_params.get("signature")
        if signature_id:
            queryset = queryset.filter(signature_id=signature_id)
        return queryset
