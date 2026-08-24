from rest_framework import serializers


class TransferHistorySerializer(serializers.Serializer):
    from_schema = serializers.CharField(allow_null=True)
    to_schema = serializers.CharField(allow_null=True)
    transferred_at = serializers.DateTimeField()
    notes = serializers.CharField(allow_blank=True, allow_null=True)


class EnrollmentHistorySerializer(serializers.Serializer):
    academic_year = serializers.CharField()
    classroom = serializers.CharField()
    class_level = serializers.CharField(allow_null=True)
    is_active = serializers.BooleanField()
    notes = serializers.CharField(allow_blank=True, allow_null=True)


class TransferTermResultSerializer(serializers.Serializer):
    academic_year = serializers.CharField()
    term = serializers.CharField()
    classroom = serializers.CharField(allow_null=True)
    total_marks = serializers.CharField()
    average_percentage = serializers.CharField()
    grade = serializers.CharField(allow_null=True)
    gpa = serializers.CharField()
    position = serializers.IntegerField(allow_null=True)


class StudentAcademicRecordsSerializer(serializers.Serializer):
    admission_number = serializers.CharField(allow_null=True)
    gender = serializers.CharField(allow_null=True)
    blood_group = serializers.CharField(allow_null=True)
    current_class = serializers.CharField(allow_null=True)
    current_level = serializers.CharField(allow_null=True)
    status = serializers.CharField()
    enrollment_history = EnrollmentHistorySerializer(many=True)
    term_results = TransferTermResultSerializer(many=True)


class StudentLookupResponseSerializer(serializers.Serializer):
    student_id = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    date_of_birth = serializers.DateField(allow_null=True)
    national_id = serializers.CharField(allow_null=True)
    current_schema = serializers.CharField(allow_null=True)
    in_transit = serializers.BooleanField()
    academic_records = StudentAcademicRecordsSerializer(allow_null=True)
    transfer_history = TransferHistorySerializer(many=True)


class TransferCompleteRequestSerializer(serializers.Serializer):
    student_id = serializers.CharField()
    notes = serializers.CharField(required=False, allow_blank=True)


class TransferCompleteResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    student_id = serializers.CharField()
    from_school = serializers.CharField(allow_null=True)
    to_school = serializers.CharField()
