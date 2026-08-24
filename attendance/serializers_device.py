from rest_framework import serializers

from attendance.models import AttendanceDevice, AttendanceScan
from attendance.models import DeviceSecurityEvent
from attendance.services.security_service import DeviceHealthService


class AttendanceDeviceSerializer(serializers.ModelSerializer):
    health = serializers.SerializerMethodField()

    def get_health(self, obj):
        return DeviceHealthService.status(obj)
    class Meta:
        model = AttendanceDevice
        fields = ("id", "name", "device_identifier", "mode", "location", "is_active", "health", "last_seen_at", "created_at", "updated_at")
        read_only_fields = ("last_seen_at", "created_at", "updated_at")


class AttendanceScanSerializer(serializers.ModelSerializer):
    masked_uid = serializers.CharField(read_only=True)
    card_number = serializers.CharField(source="credential.id_card.card_number", read_only=True)

    class Meta:
        model = AttendanceScan
        fields = ("id", "device", "credential", "card_number", "masked_uid", "request_id", "scanned_at", "received_at", "direction", "result", "processed_at", "processing_error", "metadata")
        read_only_fields = fields


class DeviceScanIngestSerializer(serializers.Serializer):
    uid = serializers.CharField(max_length=100)
    scanned_at = serializers.DateTimeField()
    direction = serializers.ChoiceField(choices=AttendanceScan.Direction.choices, required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False)


class DeviceSecurityEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceSecurityEvent
        fields = ("id", "device", "event_type", "severity", "request_id", "details", "occurrence_count", "first_occurred_at", "last_occurred_at")
        read_only_fields = fields
