from rest_framework.views import APIView
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
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


class TeacherAttendanceListView(APIView):

    queryset = TeachersAttendance.objects.all()
    serializer_class = TeacherAttendanceSerializer
    pagination_class = PageNumberPagination
    filter_backends = (SearchFilter,)
    search_fields = ["teacher__fname", "date"]

    def get(self, request):
        attendances = TeachersAttendance.objects.all()
        serializer = TeacherAttendanceSerializer(attendances, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = TeacherAttendanceSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TeacherAttendanceDetailView(RetrieveUpdateDestroyAPIView):
    """
    API View to handle retrieve, update, and delete operations for a single TeacherAttendance record.
    """
    serializer_class = TeacherAttendanceSerializer
    queryset = TeachersAttendance.objects.all()
    lookup_field = 'pk'

class StudentAttendanceListView(ListCreateAPIView):
    """
    API View to handle listing and creating StudentAttendance records.
    """
    serializer_class = StudentAttendanceSerializer
    queryset = StudentAttendance.objects.all()

class StudentAttendanceDetailView(RetrieveUpdateDestroyAPIView):
    """
    API View to handle retrieve, update, and delete operations for a single StudentAttendance record.
    """
    serializer_class = StudentAttendanceSerializer
    queryset = StudentAttendance.objects.all()
    lookup_field = 'pk'


class PeriodAttendanceListView(ListCreateAPIView):
    """
    API View to handle listing and creating PeriodAttendance records.
    """
    serializer_class = PeriodAttendanceSerializer
    queryset = PeriodAttendance.objects.all()


class PeriodAttendanceDetailView(RetrieveUpdateDestroyAPIView):
    """
    API View to handle retrieve, update, and delete operations for a single PeriodAttendance record.
    """
    serializer_class = PeriodAttendanceSerializer
    queryset = PeriodAttendance.objects.all()
    lookup_field = 'pk'
