from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.filters import SearchFilter
from .models import TeachersAttendance, StudentAttendance, PeriodAttendance
from .serializers import (
    TeacherAttendanceSerializer,
    StudentAttendanceSerializer,
    PeriodAttendanceSerializer,
)
from .permissions import CanReadAssignedAttendance, is_attendance_admin, teacher_classroom_ids


class TeacherAttendanceListView(APIView):
    permission_classes = [CanReadAssignedAttendance]

    queryset = TeachersAttendance.objects.all()
    serializer_class = TeacherAttendanceSerializer
    pagination_class = PageNumberPagination
    filter_backends = (SearchFilter,)
    search_fields = ["teacher__user__first_name", "teacher__user__last_name", "date"]

    def get(self, request):
        attendances = TeachersAttendance.objects.all()
        if not is_attendance_admin(request.user):
            attendances = attendances.filter(teacher=getattr(request.user, "teacher", None))
        serializer = TeacherAttendanceSerializer(attendances, many=True)
        return Response(serializer.data)


class TeacherAttendanceDetailView(RetrieveAPIView):
    """
    API View to handle retrieve, update, and delete operations for a single TeacherAttendance record.
    """
    serializer_class = TeacherAttendanceSerializer
    queryset = TeachersAttendance.objects.all()
    permission_classes = [CanReadAssignedAttendance]
    lookup_field = 'pk'

    def get_queryset(self):
        queryset = super().get_queryset()
        if is_attendance_admin(self.request.user):
            return queryset
        return queryset.filter(teacher=getattr(self.request.user, "teacher", None))

class PeriodAttendanceListView(ListAPIView):
    """
    API View to handle listing and creating PeriodAttendance records.
    """
    serializer_class = PeriodAttendanceSerializer
    queryset = PeriodAttendance.objects.all()
    permission_classes = [CanReadAssignedAttendance]

    def get_queryset(self):
        queryset = super().get_queryset()
        if is_attendance_admin(self.request.user):
            return queryset
        return queryset.filter(student__classroom_id__in=teacher_classroom_ids(self.request.user))


class PeriodAttendanceDetailView(RetrieveAPIView):
    """
    API View to handle retrieve, update, and delete operations for a single PeriodAttendance record.
    """
    serializer_class = PeriodAttendanceSerializer
    queryset = PeriodAttendance.objects.all()
    permission_classes = [CanReadAssignedAttendance]
    lookup_field = 'pk'

    def get_queryset(self):
        queryset = super().get_queryset()
        if is_attendance_admin(self.request.user):
            return queryset
        return queryset.filter(student__classroom_id__in=teacher_classroom_ids(self.request.user))
