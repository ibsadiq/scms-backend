"""
Result Computation Views (Phase 1.1)
Handles API endpoints for result computation, publishing, and viewing.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import TermResult, SubjectResult
from .serializers import (
    TermResultListSerializer,
    TermResultDetailSerializer,
    SubjectResultSerializer,
    ResultComputationRequestSerializer,
    PublishResultsSerializer
)
from .services import ResultComputationService


class TermResultViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing computed term results.

    Endpoints:
    - GET /api/examination/results/ - List all results
    - GET /api/examination/results/{id}/ - Get detailed result
    - PATCH /api/examination/results/{id}/ - Update remarks
    - POST /api/examination/results/compute/ - Compute results
    - POST /api/examination/results/publish/ - Publish/unpublish results
    - GET /api/examination/results/by_student/ - Get student results
    - GET /api/examination/results/by_classroom/ - Get classroom results
    """
    permission_classes = [IsAuthenticated]
    queryset = TermResult.objects.all().select_related(
        'student',
        'term',
        'academic_year',
        'classroom',
        'computed_by'
    ).prefetch_related('subject_results__subject', 'subject_results__teacher')

    def get_serializer_class(self):
        """Use different serializers for list vs detail"""
        if self.action == 'retrieve':
            return TermResultDetailSerializer
        return TermResultListSerializer

    def get_queryset(self):
        """Filter results based on user permissions and query params"""
        queryset = super().get_queryset()

        # If not staff, only show published results
        if not self.request.user.is_staff:
            queryset = queryset.filter(is_published=True)

        # Filter by student if provided
        student_id = self.request.query_params.get('student')
        if student_id:
            queryset = queryset.filter(student_id=student_id)

        # Filter by term if provided
        term_id = self.request.query_params.get('term')
        if term_id:
            queryset = queryset.filter(term_id=term_id)

        # Filter by classroom if provided
        classroom_id = self.request.query_params.get('classroom')
        if classroom_id:
            queryset = queryset.filter(classroom_id=classroom_id)

        return queryset

    @action(detail=False, methods=['post'])
    def compute(self, request):
        """
        Compute results for a classroom and term.

        Request body:
        {
            "term_id": 1,
            "classroom_id": 2,
            "grade_scale_id": 3,  // Optional
            "recompute": false
        }
        """
        serializer = ResultComputationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        term = serializer.validated_data['term']
        classroom = serializer.validated_data['classroom']
        grade_scale = serializer.validated_data.get('grade_scale')
        recompute = serializer.validated_data.get('recompute', False)

        try:
            # Initialize computation service
            service = ResultComputationService(
                term=term,
                classroom=classroom,
                computed_by=request.user,
                grade_scale=grade_scale
            )

            # Compute or recompute
            if recompute:
                results = service.recompute_results()
            else:
                # Check if results already exist
                existing = TermResult.objects.filter(
                    term=term,
                    classroom=classroom
                ).exists()

                if existing:
                    return Response(
                        {
                            'error': 'Results already exist for this classroom and term. '
                                   'Set recompute=true to recompute.'
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )

                results = service.compute_results_for_classroom()

            return Response({
                'message': 'Results computed successfully',
                'summary': results
            }, status=status.HTTP_201_CREATED)

        except DjangoValidationError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': f'Computation failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def publish(self, request):
        """
        Publish or unpublish results for a classroom and term.

        Request body:
        {
            "term_id": 1,
            "classroom_id": 2,
            "action": "publish"  // or "unpublish"
        }
        """
        serializer = PublishResultsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        term = serializer.validated_data['term']
        classroom = serializer.validated_data['classroom']
        action_type = serializer.validated_data['action']

        try:
            if action_type == 'publish':
                ResultComputationService.publish_results(term, classroom)
                message = 'Results published successfully'
            else:
                ResultComputationService.unpublish_results(term, classroom)
                message = 'Results unpublished successfully'

            return Response({
                'message': message,
                'term': term.name,
                'classroom': str(classroom)
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {'error': f'Action failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def by_student(self, request):
        """
        Get all results for a specific student.

        Query params:
        - student_id: Student ID (required)
        - term_id: Filter by term (optional)
        """
        student_id = request.query_params.get('student_id')
        if not student_id:
            return Response(
                {'error': 'student_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        queryset = self.get_queryset().filter(student_id=student_id)

        # Optional: filter by term
        term_id = request.query_params.get('term_id')
        if term_id:
            queryset = queryset.filter(term_id=term_id)

        # Order by most recent first
        queryset = queryset.order_by('-academic_year__start_date', '-term__start_date')

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_classroom(self, request):
        """
        Get all results for a specific classroom and term.

        Query params:
        - classroom_id: Classroom ID (required)
        - term_id: Term ID (required)
        """
        classroom_id = request.query_params.get('classroom_id')
        term_id = request.query_params.get('term_id')

        if not classroom_id or not term_id:
            return Response(
                {'error': 'classroom_id and term_id parameters are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        queryset = self.get_queryset().filter(
            classroom_id=classroom_id,
            term_id=term_id
        ).order_by('position_in_class')

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        """
        Allow updating only remarks fields.
        """
        instance = self.get_object()

        # Only allow updating remarks
        allowed_fields = ['class_teacher_remarks', 'principal_remarks']
        update_data = {
            k: v for k, v in request.data.items()
            if k in allowed_fields
        }

        serializer = self.get_serializer(instance, data=update_data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(serializer.data)


class SubjectResultViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing subject results.
    Subject results are computed automatically and cannot be directly modified.

    Endpoints:
    - GET /api/examination/subject-results/ - List all subject results
    - GET /api/examination/subject-results/{id}/ - Get subject result details
    - GET /api/examination/subject-results/by_term_result/ - Get by term result
    """
    permission_classes = [IsAuthenticated]
    queryset = SubjectResult.objects.all().select_related(
        'term_result',
        'subject',
        'teacher'
    )
    serializer_class = SubjectResultSerializer

    def get_queryset(self):
        """Filter based on published status for non-staff"""
        queryset = super().get_queryset()

        # If not staff, only show published results
        if not self.request.user.is_staff:
            queryset = queryset.filter(term_result__is_published=True)

        return queryset

    @action(detail=False, methods=['get'])
    def by_term_result(self, request):
        """
        Get all subject results for a specific term result.

        Query params:
        - term_result_id: TermResult ID (required)
        """
        term_result_id = request.query_params.get('term_result_id')
        if not term_result_id:
            return Response(
                {'error': 'term_result_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        queryset = self.get_queryset().filter(term_result_id=term_result_id)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
