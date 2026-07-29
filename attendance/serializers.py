from rest_framework import serializers
from .models import (
    TeachersAttendance,
    AttendanceStatus,
    StudentAttendance,
    PeriodAttendance,
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
            'created_at', 'updated_at'
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
            'status', 'remarks'
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
