from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from academic.permissions import IsSchoolAdmin
from attendance.models import StudentTermAttendanceSummary
from attendance.serializers import StudentTermAttendanceSummarySerializer
from attendance.services import AttendanceSummaryService


class StudentTermAttendanceSummaryViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsSchoolAdmin]
    serializer_class = StudentTermAttendanceSummarySerializer
    queryset = StudentTermAttendanceSummary.objects.select_related(
        "student", "term", "term__academic_year", "entered_by"
    )
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        queryset = super().get_queryset()
        student_id = self.request.query_params.get("student")
        term_id = self.request.query_params.get("term")
        classroom_id = self.request.query_params.get("classroom")
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        if term_id:
            queryset = queryset.filter(term_id=term_id)
        if classroom_id:
            queryset = queryset.filter(student__classroom_id=classroom_id)
        return queryset

    def perform_create(self, serializer):
        summary = AttendanceSummaryService.save_manual_summary(
            entered_by=self.request.user,
            **serializer.validated_data,
        )
        serializer.instance = summary

    def perform_update(self, serializer):
        instance = serializer.instance
        values = {
            "student": instance.student,
            "term": instance.term,
            "school_days": serializer.validated_data.get("school_days", instance.school_days),
            "days_present": serializer.validated_data.get("days_present", instance.days_present),
            "days_absent": serializer.validated_data.get("days_absent", instance.days_absent),
            "times_late": serializer.validated_data.get("times_late", instance.times_late),
            "notes": serializer.validated_data.get("notes", instance.notes),
            "entered_by": self.request.user,
        }
        serializer.instance = AttendanceSummaryService.save_manual_summary(**values)
