from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django_filters import FilterSet
from django_filters import CharFilter, NumberFilter

from .models import AllocatedSubject
from .serializers_allocation import AllocatedSubjectSerializer, AllocatedSubjectListSerializer


class AllocatedSubjectFilter(FilterSet):
    """Filter for AllocatedSubject"""
    teacher = NumberFilter(field_name='teacher_name')
    subject = NumberFilter(field_name='subject')
    class_room = NumberFilter(field_name='class_room')
    academic_year = NumberFilter(field_name='academic_year')
    term = NumberFilter(field_name='term')

    class Meta:
        model = AllocatedSubject
        fields = ['teacher', 'subject', 'class_room', 'academic_year', 'term']


class AllocatedSubjectViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing teacher class allocations (AllocatedSubject).
    
    Endpoints:
    - GET /api/academic/allocated-subjects/ - List all allocations
    - POST /api/academic/allocated-subjects/ - Create new allocation
    - GET /api/academic/allocated-subjects/{id}/ - Get allocation details
    - PUT/PATCH /api/academic/allocated-subjects/{id}/ - Update allocation
    - DELETE /api/academic/allocated-subjects/{id}/ - Delete allocation
    """
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = AllocatedSubjectFilter

    def get_queryset(self):
        """Filter allocations based on user role"""
        queryset = AllocatedSubject.objects.select_related(
            'teacher_name',
            'teacher_name__user',
            'subject',
            'class_room',
            'class_room__name',
            'academic_year',
            'term'
        ).order_by('-academic_year', 'class_room', 'subject')

        # If user is a teacher, only show their allocations
        if self.request.user.is_teacher:
            try:
                from .models import Teacher
                teacher = Teacher.objects.get(user=self.request.user)
                queryset = queryset.filter(teacher_name=teacher)
            except Teacher.DoesNotExist:
                return AllocatedSubject.objects.none()

        return queryset

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        from schedule.models import TimetableEntry
        TimetableEntry.objects.filter(subject=instance).delete()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_serializer_class(self):
        """Use list serializer for list actions"""
        if self.action == 'list':
            return AllocatedSubjectListSerializer
        return AllocatedSubjectSerializer

    @action(detail=False, methods=['get'])
    def by_teacher(self, request):
        """
        Get allocations for a specific teacher
        ?teacher_id=<teacher_id>
        """
        teacher_id = request.query_params.get('teacher_id')
        if not teacher_id:
            return Response(
                {'error': 'teacher_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        allocations = self.get_queryset().filter(teacher_name_id=teacher_id)
        serializer = AllocatedSubjectListSerializer(allocations, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_classroom(self, request):
        """
        Get allocations for a specific classroom
        ?classroom_id=<classroom_id>
        """
        classroom_id = request.query_params.get('classroom_id')
        if not classroom_id:
            return Response(
                {'error': 'classroom_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        allocations = self.get_queryset().filter(class_room_id=classroom_id)
        serializer = AllocatedSubjectListSerializer(allocations, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_subject(self, request):
        """
        Get allocations for a specific subject
        ?subject_id=<subject_id>
        """
        subject_id = request.query_params.get('subject_id')
        if not subject_id:
            return Response(
                {'error': 'subject_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        allocations = self.get_queryset().filter(subject_id=subject_id)
        serializer = AllocatedSubjectListSerializer(allocations, many=True)
        return Response(serializer.data)
