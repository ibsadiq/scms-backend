from rest_framework import serializers

from attendance.models import AttendanceScan


class AttendanceClassSummaryValuesSerializer(serializers.Serializer):
    attendance_rate = serializers.FloatField()
    present = serializers.IntegerField()
    absent = serializers.IntegerField()
    total_students = serializers.IntegerField()
    total_days = serializers.IntegerField()


class AttendanceClassSummarySerializer(serializers.Serializer):
    summary = AttendanceClassSummaryValuesSerializer()


class BulkAttendanceRecordSerializer(serializers.Serializer):
    student = serializers.IntegerField()
    status = serializers.CharField(default="Present")
    remarks = serializers.CharField(required=False, allow_blank=True)


class BulkAttendanceRequestSerializer(serializers.Serializer):
    classroom = serializers.IntegerField()
    date = serializers.DateField()
    records = BulkAttendanceRecordSerializer(many=True)


class BulkAttendanceErrorSerializer(serializers.Serializer):
    student_id = serializers.IntegerField(required=False)
    error = serializers.CharField()


class BulkAttendanceResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    created = serializers.IntegerField()
    updated = serializers.IntegerField()
    errors = BulkAttendanceErrorSerializer(many=True, allow_null=True)


class DeviceScanResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    result = serializers.CharField()
    direction = serializers.ChoiceField(
        choices=AttendanceScan.Direction.choices,
        allow_blank=True,
        allow_null=True,
        required=False,
    )
    scan_id = serializers.IntegerField(required=False)
    attendance_status = serializers.CharField(allow_null=True, required=False)
