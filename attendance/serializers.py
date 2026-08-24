from rest_framework import serializers
from .models import (
    TeachersAttendance,
    AttendanceStatus,
    StudentAttendance,
    PeriodAttendance,
    StudentTermAttendanceSummary,
)


class AttendanceStatusSerializer(serializers.ModelSerializer):

    class Meta:
        model = AttendanceStatus
        fields = "__all__"


class TeacherAttendanceSerializer(serializers.ModelSerializer):
    teacher = (
        serializers.StringRelatedField()
    )  # Display teacher's name instead of the ID
    status = serializers.StringRelatedField()  # Display status name instead of ID
    date = serializers.DateField(format="%Y-%m-%d")  # Date format in response

    class Meta:
        model = TeachersAttendance
        fields = ["id", "teacher", "date", "time_in", "time_out", "status", "notes"]




class StudentAttendanceSerializer(serializers.ModelSerializer):
    """
    Full serializer for attendance records.
    """
    student_id = serializers.IntegerField(source='student.id', read_only=True)
    first_name = serializers.CharField(source='student.first_name', read_only=True)
    last_name = serializers.CharField(source='student.last_name', read_only=True)
    admission_number = serializers.CharField(source='student.admission_number', read_only=True)
    
    # Keep backward-compatible 'student' string
    student = serializers.CharField(source='student.__str__', read_only=True)
    
    # Map 'notes' model field to 'remarks' in API for frontend consistency
    remarks = serializers.CharField(source='notes', required=False, allow_blank=True)
    
    # Status as plain string name
    status = serializers.CharField(source='status.name', read_only=True)
    
    # Classroom as plain string name
    ClassRoom = serializers.CharField(source='ClassRoom.name', read_only=True)
    
    # Marked by teacher name
    marked_by_name = serializers.CharField(source='marked_by.get_full_name', read_only=True)
    
    date = serializers.DateField(format="%Y-%m-%d")

    class Meta:
        model = StudentAttendance
        fields = [
            'id', 'student_id', 'student', 'first_name', 'last_name',
            'admission_number', 'date', 'ClassRoom', 'term', 
            'status', 'remarks', 'notes', 'marked_by', 'marked_by_name',
            'time_in', 'time_out', 'created_at', 'updated_at'
        ]


class StudentAttendanceListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for list views (what the frontend uses).
    """
    student_id = serializers.IntegerField(source='student.id', read_only=True)
    first_name = serializers.CharField(source='student.first_name', read_only=True)
    last_name = serializers.CharField(source='student.last_name', read_only=True)
    admission_number = serializers.CharField(source='student.admission_number', read_only=True)
    status = serializers.CharField(source='status.name', read_only=True)
    remarks = serializers.CharField(source='notes', required=False, allow_blank=True)
    ClassRoom = serializers.CharField(source='ClassRoom.name', read_only=True)
    date = serializers.DateField(format="%Y-%m-%d")

    class Meta:
        model = StudentAttendance
        fields = [
            'id', 'student_id', 'first_name', 'last_name',
            'admission_number', 'date', 'ClassRoom', 'term',
            'status', 'remarks', 'time_in', 'time_out'
        ]

class PeriodAttendanceSerializer(serializers.ModelSerializer):
    student = serializers.StringRelatedField()  # Display student name instead of ID
    status = serializers.StringRelatedField()  # Display status name instead of ID
    date = serializers.DateField(format="%Y-%m-%d")  # Date format in response

    class Meta:
        model = PeriodAttendance
        fields = [
            "id",
            "student",
            "date",
            "period",
            "status",
            "reason_for_absence",
            "notes",
        ]


class StudentTermAttendanceSummarySerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True)
    entered_by_name = serializers.CharField(source="entered_by.get_full_name", read_only=True)
    attendance_percentage = serializers.FloatField(read_only=True)

    class Meta:
        model = StudentTermAttendanceSummary
        fields = [
            "id", "student", "student_name", "term", "term_name", "school_days",
            "days_present", "days_absent", "times_late", "attendance_percentage",
            "source", "entered_by", "entered_by_name", "notes", "created_at", "updated_at",
        ]
        read_only_fields = ["source", "entered_by", "created_at", "updated_at"]
        validators = []

    def validate(self, attrs):
        instance = self.instance
        school_days = attrs.get("school_days", getattr(instance, "school_days", None))
        days_present = attrs.get("days_present", getattr(instance, "days_present", None))
        days_absent = attrs.get("days_absent", getattr(instance, "days_absent", None))
        times_late = attrs.get("times_late", getattr(instance, "times_late", 0))
        errors = {}
        for field, value in {
            "school_days": school_days, "days_present": days_present,
            "days_absent": days_absent, "times_late": times_late,
        }.items():
            if value is not None and value < 0:
                errors[field] = "Attendance counts cannot be negative."
        if school_days is not None and days_present is not None and days_present > school_days:
            errors["days_present"] = "Days present cannot exceed school days."
        if school_days is not None and days_absent is not None and days_absent > school_days:
            errors["days_absent"] = "Days absent cannot exceed school days."
        if None not in (school_days, days_present, days_absent) and days_present + days_absent > school_days:
            errors["days_absent"] = "Present and absent days combined cannot exceed school days."
        if instance:
            if "student" in attrs and attrs["student"] != instance.student:
                errors["student"] = "The student cannot be changed after creation."
            if "term" in attrs and attrs["term"] != instance.term:
                errors["term"] = "The term cannot be changed after creation."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs
