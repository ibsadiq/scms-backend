from rest_framework import serializers


class AdministrativeStudentReportSerializer(serializers.Serializer):
    admission_number = serializers.CharField()
    full_name = serializers.CharField()
    class_name = serializers.CharField()
    grade_level = serializers.CharField()
    status = serializers.CharField()


class TeacherAcademicReportSerializer(AdministrativeStudentReportSerializer):
    attendance_rate = serializers.FloatField(allow_null=True)
    total_present = serializers.IntegerField()
    total_absent = serializers.IntegerField()
    average_grade = serializers.CharField(allow_null=True)


class PaymentByMethodSerializer(serializers.Serializer):
    method = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    count = serializers.IntegerField()


class RevenueByTypeSerializer(serializers.Serializer):
    fee_type = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)


class FinanceDefaulterSerializer(serializers.Serializer):
    admission_number = serializers.CharField()
    student_name = serializers.CharField()
    class_name = serializers.CharField()
    balance = serializers.DecimalField(max_digits=12, decimal_places=2)


class FinancialReportSerializer(serializers.Serializer):
    total_collected = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_outstanding = serializers.DecimalField(max_digits=14, decimal_places=2)
    collection_rate = serializers.FloatField()
    payment_by_method = PaymentByMethodSerializer(many=True)
    revenue_by_type = RevenueByTypeSerializer(many=True)
    defaulters = FinanceDefaulterSerializer(many=True)


class AttendanceRecordSerializer(serializers.Serializer):
    date = serializers.DateField()
    class_name = serializers.CharField()
    total_students = serializers.IntegerField()
    present = serializers.IntegerField()
    absent = serializers.IntegerField()
    attendance_rate = serializers.FloatField()


class AttendanceSummarySerializer(serializers.Serializer):
    total_days = serializers.IntegerField()
    average_attendance = serializers.FloatField()
    total_absences = serializers.IntegerField()


class AttendanceReportSerializer(serializers.Serializer):
    records = AttendanceRecordSerializer(many=True)
    summary = AttendanceSummarySerializer()
