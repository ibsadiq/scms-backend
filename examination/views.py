from rest_framework import viewsets, status, parsers
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
    SubjectResult,
    MarkedScript
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
    PublishResultsSerializer,
    MarkedScriptListSerializer,
    MarkedScriptCreateSerializer,
    MarkedScriptBulkUploadSerializer
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


class MarkedScriptViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing marked exam scripts uploaded by teachers.

    Endpoints:
    - GET /api/examination/marked-scripts/ - List all marked scripts (filtered by teacher)
    - POST /api/examination/marked-scripts/ - Upload a marked script
    - GET /api/examination/marked-scripts/{id}/ - Get marked script details
    - PUT /api/examination/marked-scripts/{id}/ - Update marked script metadata
    - DELETE /api/examination/marked-scripts/{id}/ - Delete marked script
    - GET /api/examination/marked-scripts/by_exam/?exam_id={id} - Get scripts for specific exam
    - GET /api/examination/marked-scripts/by_student/?student_id={id} - Get scripts for specific student
    - POST /api/examination/marked-scripts/bulk_upload/ - Upload multiple marked scripts
    - PATCH /api/examination/marked-scripts/{id}/toggle_visibility/ - Toggle visibility to student/parent
    """
    permission_classes = [IsAuthenticated]
    queryset = MarkedScript.objects.all().select_related(
        'exam', 'student', 'subject', 'uploaded_by', 'marks_entry'
    )
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]

    def get_serializer_class(self):
        """Use different serializers for list vs create/update"""
        if self.action in ['create', 'update', 'partial_update']:
            return MarkedScriptCreateSerializer
        return MarkedScriptListSerializer

    def get_queryset(self):
        """
        Filter queryset based on user role.
        Teachers see only their uploads, admins see all.
        """
        user = self.request.user
        queryset = super().get_queryset()

        # Admins see everything
        if user.is_superuser:
            return queryset

        # Teachers see only their uploads
        if user.is_staff and hasattr(user, 'teacher'):
            return queryset.filter(uploaded_by=user.teacher)

        # Default: no access
        return queryset.none()

    def perform_create(self, serializer):
        """Set the uploaded_by teacher when creating a marked script"""
        # Get teacher from user
        teacher = self.request.user.teacher
        serializer.save(uploaded_by=teacher)

    @action(detail=False, methods=['get'])
    def by_exam(self, request):
        """Get all marked scripts for a specific examination"""
        exam_id = request.query_params.get('exam_id')
        if not exam_id:
            return Response(
                {'error': 'exam_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        scripts = self.get_queryset().filter(exam_id=exam_id)
        serializer = self.get_serializer(scripts, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_student(self, request):
        """Get all marked scripts for a specific student"""
        student_id = request.query_params.get('student_id')
        if not student_id:
            return Response(
                {'error': 'student_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        scripts = self.get_queryset().filter(student_id=student_id)
        serializer = self.get_serializer(scripts, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_subject(self, request):
        """Get all marked scripts for a specific subject"""
        subject_id = request.query_params.get('subject_id')
        if not subject_id:
            return Response(
                {'error': 'subject_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        scripts = self.get_queryset().filter(subject_id=subject_id)
        serializer = self.get_serializer(scripts, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], parser_classes=[parsers.MultiPartParser, parsers.FormParser])
    def bulk_upload(self, request):
        """
        Bulk upload multiple marked scripts.
        Accepts multiple files with corresponding metadata.
        """
        files = request.FILES.getlist('files')
        if not files:
            return Response(
                {'error': 'No files provided. Use "files" field for multiple uploads.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get common data
        exam_id = request.data.get('exam_id')
        subject_id = request.data.get('subject_id')
        visible_to_student = request.data.get('visible_to_student', 'false').lower() == 'true'
        visible_to_parent = request.data.get('visible_to_parent', 'false').lower() == 'true'
        notes = request.data.get('notes', '')

        if not exam_id or not subject_id:
            return Response(
                {'error': 'exam_id and subject_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get student IDs (comma-separated or list)
        student_ids_raw = request.data.getlist('student_ids') or [request.data.get('student_ids')]
        student_ids = []
        for item in student_ids_raw:
            if item:
                student_ids.extend([s.strip() for s in str(item).split(',')])

        if len(student_ids) != len(files):
            return Response(
                {'error': f'Number of student IDs ({len(student_ids)}) must match number of files ({len(files)})'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create marked scripts
        created_scripts = []
        errors = []
        teacher = request.user.teacher

        for idx, (file, student_id) in enumerate(zip(files, student_ids)):
            try:
                # Validate and create
                from academic.models import Student, Subject
                from .models import ExaminationListHandler

                exam = ExaminationListHandler.objects.get(id=exam_id)
                subject = Subject.objects.get(id=subject_id)
                student = Student.objects.get(id=student_id)

                # Create marked script
                marked_script = MarkedScript.objects.create(
                    exam=exam,
                    student=student,
                    subject=subject,
                    script_file=file,
                    uploaded_by=teacher,
                    notes=notes,
                    visible_to_student=visible_to_student,
                    visible_to_parent=visible_to_parent
                )

                created_scripts.append({
                    'id': marked_script.id,
                    'student_id': student_id,
                    'student_name': student.full_name,
                    'file_name': marked_script.file_name
                })

            except Exception as e:
                errors.append({
                    'file_index': idx,
                    'student_id': student_id,
                    'error': str(e)
                })

        response_data = {
            'message': f'Uploaded {len(created_scripts)} of {len(files)} files successfully',
            'created': created_scripts,
            'errors': errors
        }

        if errors:
            return Response(response_data, status=status.HTTP_207_MULTI_STATUS)
        return Response(response_data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'])
    def toggle_visibility(self, request, pk=None):
        """
        Toggle visibility of marked script to students and/or parents.
        """
        marked_script = self.get_object()

        visible_to_student = request.data.get('visible_to_student')
        visible_to_parent = request.data.get('visible_to_parent')

        if visible_to_student is not None:
            marked_script.visible_to_student = visible_to_student

        if visible_to_parent is not None:
            marked_script.visible_to_parent = visible_to_parent

        marked_script.save()

        serializer = self.get_serializer(marked_script)
        return Response({
            'message': 'Visibility updated successfully',
            'data': serializer.data
        })
