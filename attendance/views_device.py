from django.db import IntegrityError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from academic.permissions import IsSchoolAdmin
from django.db.models import Count
from django.db.models.functions import TruncDate
from attendance.models import AttendanceDevice, AttendanceScan, DeviceSecurityEvent
from attendance.serializers_device import AttendanceDeviceSerializer, AttendanceScanSerializer, DeviceScanIngestSerializer, DeviceSecurityEventSerializer
from attendance.services import AttendanceDeviceService, AttendanceScanService, DeviceAuthenticationError, DeviceRateLimitExceeded, DeviceRateLimitService, DeviceSecurityEventService
from attendance.schema_serializers import DeviceScanResponseSerializer
from drf_spectacular.utils import OpenApiParameter, extend_schema


class AttendanceDeviceViewSet(viewsets.ModelViewSet):
    queryset = AttendanceDevice.objects.all()
    serializer_class = AttendanceDeviceSerializer
    permission_classes = (IsAuthenticated, IsSchoolAdmin)
    http_method_names = ("get", "post", "put", "patch", "head", "options")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device, secret = AttendanceDeviceService.register(**serializer.validated_data)
        data = self.get_serializer(device).data
        data["secret"] = secret
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("post",), url_path="rotate-secret")
    def rotate_secret(self, request, pk=None):
        return Response({"secret": AttendanceDeviceService.rotate_secret(self.get_object())})

    @action(detail=True, methods=("post",))
    def disable(self, request, pk=None):
        device = self.get_object()
        device.is_active = False
        device.save(update_fields=("is_active", "updated_at"))
        return Response(self.get_serializer(device).data)


class AttendanceScanViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AttendanceScan.objects.select_related("device", "credential__id_card")
    serializer_class = AttendanceScanSerializer
    permission_classes = (IsAuthenticated, IsSchoolAdmin)

    def get_queryset(self):
        queryset = super().get_queryset()
        mapping = {"device": "device", "result": "result", "direction": "direction", "credential": "credential", "card": "credential__id_card", "student": "credential__id_card__student", "staff": "credential__id_card__staff", "date_from": "scanned_at__date__gte", "date_to": "scanned_at__date__lte"}
        for query_key, field in mapping.items():
            value = self.request.query_params.get(query_key)
            if value:
                queryset = queryset.filter(**{field: value})
        return queryset[:1000]

    @action(detail=False, methods=("get",), url_path="unknown-summary")
    def unknown_summary(self, request):
        queryset = self.get_queryset().filter(result=AttendanceScan.Result.UNKNOWN_CARD)
        data = queryset.annotate(date=TruncDate("scanned_at")).values("device", "date").annotate(count=Count("id")).order_by("-date", "device")[:1000]
        return Response(data)


class DeviceSecurityEventViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DeviceSecurityEvent.objects.select_related("device")
    serializer_class = DeviceSecurityEventSerializer
    permission_classes = (IsAuthenticated, IsSchoolAdmin)

    def get_queryset(self):
        queryset = super().get_queryset()
        for field in ("device", "event_type", "severity"):
            if self.request.query_params.get(field):
                queryset = queryset.filter(**{field: self.request.query_params[field]})
        return queryset[:1000]


class DeviceScanIngestView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(
        request=DeviceScanIngestSerializer,
        parameters=[
            OpenApiParameter("X-Device-ID", str, location=OpenApiParameter.HEADER, required=True),
            OpenApiParameter("X-Device-Secret", str, location=OpenApiParameter.HEADER, required=True),
            OpenApiParameter("X-Request-Timestamp", str, location=OpenApiParameter.HEADER, required=True),
            OpenApiParameter("X-Request-ID", str, location=OpenApiParameter.HEADER, required=True),
            OpenApiParameter("X-Device-Signature", str, location=OpenApiParameter.HEADER, required=True),
        ],
        responses={200: DeviceScanResponseSerializer, 401: DeviceScanResponseSerializer,
                   409: DeviceScanResponseSerializer, 429: DeviceScanResponseSerializer},
        auth=[],
    )
    def post(self, request):
        raw_body = request.body
        try:
            device = AttendanceDeviceService.authenticate(
                identifier=request.headers.get("X-Device-ID"), secret=request.headers.get("X-Device-Secret"),
                request_timestamp=request.headers.get("X-Request-Timestamp"), request_id=request.headers.get("X-Request-ID"),
                signature=request.headers.get("X-Device-Signature"), method=request.method,
                path=request.path, body=raw_body,
            )
        except DeviceAuthenticationError as exc:
            return Response({"success": False, "result": exc.result}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            DeviceRateLimitService.check(device)
        except DeviceRateLimitExceeded as exc:
            DeviceSecurityEventService.record(
                device=device, event_type=DeviceSecurityEvent.EventType.RATE_LIMIT,
                severity=DeviceSecurityEvent.Severity.CRITICAL,
                request_id=request.headers.get("X-Request-ID", ""), details={"window": str(exc)},
            )
            return Response({"success": False, "result": "RATE_LIMITED"}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        serializer = DeviceScanIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            scan = AttendanceScanService.process(device=device, request_id=request.headers["X-Request-ID"], **serializer.validated_data)
        except IntegrityError:
            DeviceSecurityEventService.record(
                device=device, event_type=DeviceSecurityEvent.EventType.REPLAY_ATTEMPT,
                severity=DeviceSecurityEvent.Severity.WARNING, request_id=request.headers.get("X-Request-ID", ""),
            )
            return Response({"success": False, "result": "REPLAY_REJECTED"}, status=409)
        return Response({"success": scan.result == AttendanceScan.Result.SUCCESS, "result": scan.result, "direction": scan.direction or None, "scan_id": scan.pk, "attendance_status": scan.metadata.get("attendance_status")})
