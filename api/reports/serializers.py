# api/reports/serializers.py
from rest_framework import serializers
from academic.models import Student
from finance.models import Receipt, StudentFeeAssignment


class StudentReportSerializer(serializers.Serializer):
    """Serializer for student report data"""
    student_id = serializers.IntegerField()
    admission_number = serializers.CharField()
    full_name = serializers.CharField()
    class_name = serializers.CharField()
    grade_level = serializers.CharField()
    status = serializers.CharField()
    attendance_rate = serializers.FloatField(required=False, allow_null=True)
    total_present = serializers.IntegerField(required=False, allow_null=True)
    total_absent = serializers.IntegerField(required=False, allow_null=True)
    average_grade = serializers.CharField(required=False, allow_null=True)
    total_fees = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    fees_paid = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    balance = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)


class StudentReportSummarySerializer(serializers.Serializer):
    """Summary statistics for student report"""
    total_students = serializers.IntegerField()
    active_students = serializers.IntegerField()
    average_attendance = serializers.FloatField()
    average_balance = serializers.DecimalField(max_digits=10, decimal_places=2)


class StudentReportResponseSerializer(serializers.Serializer):
    """Complete student report response"""
    students = StudentReportSerializer(many=True)
    summary = StudentReportSummarySerializer()


class PaymentByMethodSerializer(serializers.Serializer):
    """Revenue breakdown by payment method"""
    method = serializers.CharField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    count = serializers.IntegerField()


class RevenueByTypeSerializer(serializers.Serializer):
    """Revenue breakdown by fee type"""
    fee_type = serializers.CharField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)


class DefaulterSerializer(serializers.Serializer):
    """Students with outstanding fees"""
    student_id = serializers.IntegerField()
    student_name = serializers.CharField()
    admission_number = serializers.CharField()
    class_name = serializers.CharField()
    balance = serializers.DecimalField(max_digits=10, decimal_places=2)


class FinancialReportSerializer(serializers.Serializer):
    """Complete financial report response"""
    total_collected = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_outstanding = serializers.DecimalField(max_digits=12, decimal_places=2)
    collection_rate = serializers.FloatField()
    payment_by_method = PaymentByMethodSerializer(many=True)
    revenue_by_type = RevenueByTypeSerializer(many=True)
    defaulters = DefaulterSerializer(many=True)


class AttendanceRecordSerializer(serializers.Serializer):
    """Attendance report record"""
    date = serializers.DateField()
    class_name = serializers.CharField()
    total_students = serializers.IntegerField()
    present = serializers.IntegerField()
    absent = serializers.IntegerField()
    attendance_rate = serializers.FloatField()


class AttendanceReportSummarySerializer(serializers.Serializer):
    """Summary statistics for attendance report"""
    total_days = serializers.IntegerField()
    average_attendance = serializers.FloatField()
    total_absences = serializers.IntegerField()


class AttendanceReportResponseSerializer(serializers.Serializer):
    """Complete attendance report response"""
    records = AttendanceRecordSerializer(many=True)
    summary = AttendanceReportSummarySerializer()
