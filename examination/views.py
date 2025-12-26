from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import ValidationError as DjangoValidationError
from .permissions import CanEnterMarks, CanViewResults, CanManageExaminations
from .models import (
    ExaminationListHandler,
    MarksManagement,
    Result,
    GradeScale,
    TermResult,
    SubjectResult
)
from .serializers import (
    ExaminationListSerializer,
    ExaminationCreateSerializer,
    MarksListSerializer,
    MarksCreateSerializer,
    ResultSerializer,
    GradeScaleSerializer,
    TermResultListSerializer,
    TermResultDetailSerializer,
    SubjectResultSerializer,
    ResultComputationRequestSerializer,
    PublishResultsSerializer
)
from .services import ResultComputationService


class ExaminationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing examinations/assessments.

    Endpoints:
    - GET /api/academic/assessments/ - List all assessments
    - POST /api/academic/assessments/ - Create new assessment
    - GET /api/academic/assessments/{id}/ - Get assessment details
    - PUT /api/academic/assessments/{id}/ - Update assessment
    - DELETE /api/academic/assessments/{id}/ - Delete assessment
    - GET /api/academic/assessments/active/ - List active assessments
    """
    permission_classes = [IsAuthenticated, CanManageExaminations]
    queryset = ExaminationListHandler.objects.all().select_related('created_by').prefetch_related('classrooms')

    def get_serializer_class(self):
        """Use different serializers for list vs create/update"""
        if self.action in ['create', 'update', 'partial_update']:
            return ExaminationCreateSerializer
        return ExaminationListSerializer

    def perform_create(self, serializer):
        """Set the created_by user when creating an assessment"""
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get only active (ongoing) assessments"""
        from django.utils import timezone
        active_exams = self.queryset.filter(
            start_date__lte=timezone.now().date(),
            ends_date__gte=timezone.now().date()
        )
        serializer = self.get_serializer(active_exams, many=True)
        return Response(serializer.data)


class MarksViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing student marks.
    Phase 1.3: Added permission checks for marks entry.

    Endpoints:
    - GET /api/academic/marks/ - List all marks
    - POST /api/academic/marks/ - Create/enter marks
    - GET /api/academic/marks/{id}/ - Get mark details
    - PUT /api/academic/marks/{id}/ - Update marks
    - DELETE /api/academic/marks/{id}/ - Delete marks
    - GET /api/academic/marks/by_exam/?exam_id={id} - Get marks for specific exam
    - GET /api/academic/marks/by_student/?student_id={id} - Get marks for specific student
    """
    permission_classes = [IsAuthenticated, CanEnterMarks]
    queryset = MarksManagement.objects.all().select_related(
        'exam_name', 'subject', 'student', 'created_by'
    )

    def get_serializer_class(self):
        """Use different serializers for list vs create/update"""
        if self.action in ['create', 'update', 'partial_update']:
            return MarksCreateSerializer
        return MarksListSerializer

    def perform_create(self, serializer):
        """Set the created_by user when entering marks"""
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=['get'])
    def by_exam(self, request):
        """Get all marks for a specific examination"""
        exam_id = request.query_params.get('exam_id')
        if not exam_id:
            return Response(
                {'error': 'exam_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        marks = self.queryset.filter(exam_name_id=exam_id)
        serializer = self.get_serializer(marks, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_student(self, request):
        """Get all marks for a specific student"""
        student_id = request.query_params.get('student_id')
        if not student_id:
            return Response(
                {'error': 'student_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        marks = self.queryset.filter(student_id=student_id)
        serializer = self.get_serializer(marks, many=True)
        return Response(serializer.data)


class ResultViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing student results.

    Endpoints:
    - GET /api/academic/results/ - List all results
    - POST /api/academic/results/ - Create result
    - GET /api/academic/results/{id}/ - Get result details
    - PUT /api/academic/results/{id}/ - Update result
    - DELETE /api/academic/results/{id}/ - Delete result
    - GET /api/academic/results/by_student/?student_id={id} - Get results for specific student
    """
    queryset = Result.objects.all().select_related('student', 'academic_year', 'term')
    serializer_class = ResultSerializer

    @action(detail=False, methods=['get'])
    def by_student(self, request):
        """Get all results for a specific student"""
        student_id = request.query_params.get('student_id')
        if not student_id:
            return Response(
                {'error': 'student_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        results = self.queryset.filter(student_id=student_id)
        serializer = self.get_serializer(results, many=True)
        return Response(serializer.data)


class GradeScaleViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing grade scales.

    Endpoints:
    - GET /api/academic/grade-scales/ - List all grade scales
    - POST /api/academic/grade-scales/ - Create grade scale
    - GET /api/academic/grade-scales/{id}/ - Get grade scale details
    - PUT /api/academic/grade-scales/{id}/ - Update grade scale
    - DELETE /api/academic/grade-scales/{id}/ - Delete grade scale
    """
    queryset = GradeScale.objects.all()
    serializer_class = GradeScaleSerializer
