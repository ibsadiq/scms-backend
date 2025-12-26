from django.http import JsonResponse
from django.core.management import call_command
from django.core.exceptions import ValidationError
from io import StringIO
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from .models import Period
from .serializers import PeriodSerializer, PeriodListSerializer, PeriodCreateSerializer
from academic.models import AllocatedSubject


class PeriodViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing timetable periods with conflict detection.

    Provides:
    - List all periods
    - Create new period (with conflict validation)
    - Retrieve period details
    - Update period (with conflict validation)
    - Delete period
    - Check for conflicts before saving
    """
    queryset = Period.objects.all().select_related(
        'classroom', 'subject', 'teacher', 'subject__subject'
    ).order_by('day_of_week', 'start_time')

    def get_serializer_class(self):
        """
        Use different serializers for different actions.
        """
        if self.action in ['create', 'update', 'partial_update']:
            return PeriodCreateSerializer
        return PeriodListSerializer

    def create(self, request, *args, **kwargs):
        """
        Create a new period with conflict validation.
        """
        serializer = self.get_serializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)

            # Return with nested data for display
            instance = serializer.instance
            response_serializer = PeriodListSerializer(instance)

            return Response(
                response_serializer.data,
                status=status.HTTP_201_CREATED
            )
        except ValidationError as e:
            # Handle Django model validation errors
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': f'Failed to create period: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    def update(self, request, *args, **kwargs):
        """
        Update a period with conflict validation.
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)

        try:
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)

            # Return with nested data for display
            response_serializer = PeriodListSerializer(serializer.instance)

            return Response(response_serializer.data)
        except ValidationError as e:
            # Handle Django model validation errors
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': f'Failed to update period: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['post'])
    def check_conflicts(self, request):
        """
        Check for timetable conflicts without saving.

        POST /api/timetable/check_conflicts/
        Body: {
            "classroom": 1,
            "teacher": 2,
            "day_of_week": "Monday",
            "start_time": "09:00",
            "end_time": "10:00",
            "exclude_id": 5  # Optional: ID of period being edited
        }
        """
        classroom_id = request.data.get('classroom')
        teacher_id = request.data.get('teacher')
        day_of_week = request.data.get('day_of_week')
        start_time = request.data.get('start_time')
        end_time = request.data.get('end_time')
        exclude_id = request.data.get('exclude_id')

        conflicts = []

        # Check classroom conflicts
        if classroom_id and day_of_week and start_time and end_time:
            classroom_periods = Period.objects.filter(
                classroom_id=classroom_id,
                day_of_week=day_of_week,
                is_active=True
            )

            if exclude_id:
                classroom_periods = classroom_periods.exclude(id=exclude_id)

            for period in classroom_periods:
                # Check time overlap
                if (start_time < str(period.end_time) and end_time > str(period.start_time)):
                    conflicts.append({
                        'type': 'classroom',
                        'message': f'Classroom is already scheduled from {period.start_time} to {period.end_time}',
                        'period_id': period.id,
                        'subject': str(period.subject)
                    })

        # Check teacher conflicts
        if teacher_id and day_of_week and start_time and end_time:
            teacher_periods = Period.objects.filter(
                teacher_id=teacher_id,
                day_of_week=day_of_week,
                is_active=True
            )

            if exclude_id:
                teacher_periods = teacher_periods.exclude(id=exclude_id)

            for period in teacher_periods:
                # Check time overlap
                if (start_time < str(period.end_time) and end_time > str(period.start_time)):
                    conflicts.append({
                        'type': 'teacher',
                        'message': f'Teacher is already scheduled from {period.start_time} to {period.end_time}',
                        'period_id': period.id,
                        'classroom': str(period.classroom),
                        'subject': str(period.subject)
                    })

        if conflicts:
            return Response({
                'has_conflicts': True,
                'conflicts': conflicts
            }, status=status.HTTP_200_OK)

        return Response({
            'has_conflicts': False,
            'message': 'No conflicts found'
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def by_classroom(self, request):
        """
        Get all periods for a specific classroom.

        GET /api/timetable/by_classroom/?classroom=1
        """
        classroom_id = request.query_params.get('classroom')
        if not classroom_id:
            return Response(
                {'error': 'classroom parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        periods = self.get_queryset().filter(classroom_id=classroom_id)
        serializer = PeriodListSerializer(periods, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_teacher(self, request):
        """
        Get all periods for a specific teacher.

        GET /api/timetable/by_teacher/?teacher=1
        """
        teacher_id = request.query_params.get('teacher')
        if not teacher_id:
            return Response(
                {'error': 'teacher parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        periods = self.get_queryset().filter(teacher_id=teacher_id)
        serializer = PeriodListSerializer(periods, many=True)
        return Response(serializer.data)


class PeriodCreateView(APIView):
    """
    Legacy view for creating periods via AllocatedSubject.
    Kept for backward compatibility.
    """
    def post(self, request, *args, **kwargs):
        allocated_subject_id = request.data.get("allocated_subject")
        try:
            allocated_subject = AllocatedSubject.objects.get(id=allocated_subject_id)
        except AllocatedSubject.DoesNotExist:
            return Response(
                {"error": "AllocatedSubject not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = PeriodSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(allocated_subject=allocated_subject)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


def run_generate_timetable(request):
    """
    View to trigger the timetable generation management command.
    """
    output = StringIO()
    try:
        call_command("generate_timetable", stdout=output)
        return JsonResponse({"status": "success", "message": output.getvalue()})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)})
