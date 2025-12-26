"""
Class Advancement ViewSets - API endpoints for student class movements

Phase 2.2: Class Advancement Automation

Provides endpoints for:
- Previewing class movements
- Executing class movements
- Verifying capacity
- Assigning SS1 streams
- Managing student enrollments
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import StudentClassEnrollment, Student
from administration.models import AcademicYear
from .serializers import (
    StudentClassEnrollmentSerializer,
    StreamAssignmentSerializer,
    ClassMovementPreviewSerializer,
    ClassMovementExecutionSerializer,
    CapacityWarningSerializer,
    NewClassroomNeededSerializer
)
from .services import ClassAdvancementService


class ClassAdvancementViewSet(viewsets.ViewSet):
    """
    ViewSet for class advancement operations.

    Endpoints:
    - POST /api/academic/class-advancement/preview/ - Preview movements
    - POST /api/academic/class-advancement/execute/ - Execute movements
    - POST /api/academic/class-advancement/verify/ - Verify capacity
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.service = ClassAdvancementService()

    @action(detail=False, methods=['post'])
    def preview(self, request):
        """
        Preview class movements without making changes.

        Request body:
        {
            "academic_year_id": 1,
            "promotion_ids": [1, 2, 3]  // Optional
        }

        Returns:
        {
            "summary": {
                "total_students": 150,
                "promoted_count": 130,
                "repeated_count": 15,
                "graduated_count": 5,
                "conditional_count": 0,
                "needs_stream_assignment_count": 12
            },
            "movements": {
                "promoted": [...],
                "repeated": [...],
                "graduated": [...],
                "conditional": [...]
            },
            "capacity_warnings": [...],
            "missing_streams": [...],
            "new_classrooms_needed": [...]
        }
        """
        academic_year_id = request.data.get('academic_year_id')
        promotion_ids = request.data.get('promotion_ids')

        if not academic_year_id:
            return Response(
                {'error': 'academic_year_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            academic_year = AcademicYear.objects.get(id=academic_year_id)
        except AcademicYear.DoesNotExist:
            return Response(
                {'error': f'Academic year {academic_year_id} not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            preview_data = self.service.preview_class_movements(
                academic_year=academic_year,
                promotion_ids=promotion_ids
            )

            return Response(preview_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def execute(self, request):
        """
        Execute class movements based on promotions.

        Request body:
        {
            "academic_year_id": 1,
            "new_academic_year_id": 2,
            "promotion_ids": [1, 2, 3],  // Optional
            "auto_create_classrooms": true,
            "default_teacher_id": 5  // Optional
        }

        Returns:
        {
            "message": "Successfully moved 130 students",
            "promoted": 120,
            "repeated": 10,
            "graduated": 5,
            "conditional": 0,
            "errors": [],
            "classrooms_created": ["SS1 Science B", "SS1 Arts A"],
            "enrollments_created": 130
        }
        """
        serializer = ClassMovementExecutionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        data = serializer.validated_data

        try:
            academic_year = AcademicYear.objects.get(id=data['academic_year_id'])
            new_academic_year = AcademicYear.objects.get(id=data['new_academic_year_id'])
        except AcademicYear.DoesNotExist as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            results = self.service.execute_class_movements(
                academic_year=academic_year,
                new_academic_year=new_academic_year,
                promotion_ids=data.get('promotion_ids'),
                auto_create_classrooms=data.get('auto_create_classrooms', True),
                default_teacher_id=data.get('default_teacher_id')
            )

            total_moved = results['promoted'] + results['repeated'] + results['graduated'] + results['conditional']

            return Response({
                'message': f"Successfully processed {total_moved} students",
                **results
            }, status=status.HTTP_201_CREATED)

        except DjangoValidationError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def verify(self, request):
        """
        Verify capacity before executing movements.

        Request body:
        {
            "academic_year_id": 1
        }

        Returns:
        {
            "all_classrooms_sufficient": false,
            "capacity_warnings": [...],
            "new_classrooms_needed": [...],
            "missing_stream_assignments": [...],
            "can_proceed": false
        }
        """
        academic_year_id = request.data.get('academic_year_id')

        if not academic_year_id:
            return Response(
                {'error': 'academic_year_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            academic_year = AcademicYear.objects.get(id=academic_year_id)
        except AcademicYear.DoesNotExist:
            return Response(
                {'error': f'Academic year {academic_year_id} not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            verification = self.service.verify_capacity(academic_year)
            return Response(verification, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class StreamAssignmentViewSet(viewsets.ViewSet):
    """
    ViewSet for managing SS1 stream assignments.

    Endpoints:
    - POST /api/academic/stream-assignments/assign/ - Admin assigns streams
    - PUT /api/academic/stream-assignments/{student_id}/prefer/ - Student sets preference
    - GET /api/academic/stream-assignments/pending/ - List students needing assignment
    """
    permission_classes = [IsAuthenticated]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.service = ClassAdvancementService()

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated, IsAdminUser])
    def assign(self, request):
        """
        Admin assigns final streams to SS1 students.

        Request body:
        {
            "assignments": [
                {"student_id": 123, "assigned_stream": "science"},
                {"student_id": 124, "assigned_stream": "commercial"},
                {"student_id": 125, "assigned_stream": "arts"}
            ]
        }

        Returns:
        {
            "message": "Successfully assigned streams to 3 students",
            "assigned": 3,
            "errors": []
        }
        """
        assignments = request.data.get('assignments', [])

        if not assignments:
            return Response(
                {'error': 'assignments list is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Build stream assignments dict
        student_ids = [a['student_id'] for a in assignments]
        stream_assignments = {a['student_id']: a['assigned_stream'] for a in assignments}

        try:
            results = self.service.assign_ss1_streams(
                student_ids=student_ids,
                stream_assignments=stream_assignments
            )

            return Response({
                'message': f"Successfully assigned streams to {results['assigned']} students",
                **results
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['put'])
    def prefer(self, request, pk=None):
        """
        Student/Parent sets stream preference for SS1.

        URL: /api/academic/stream-assignments/{student_id}/prefer/

        Request body:
        {
            "preferred_stream": "science"
        }

        Returns:
        {
            "message": "Stream preference updated successfully",
            "student_id": 123,
            "preferred_stream": "science"
        }
        """
        preferred_stream = request.data.get('preferred_stream')

        if not preferred_stream:
            return Response(
                {'error': 'preferred_stream is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if preferred_stream not in ['science', 'commercial', 'arts']:
            return Response(
                {'error': 'preferred_stream must be one of: science, commercial, arts'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            student = Student.objects.get(id=pk)
        except Student.DoesNotExist:
            return Response(
                {'error': f'Student {pk} not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check permissions: admin, student themselves, or their parent
        if not request.user.is_staff:
            # Check if user is the student's parent
            if hasattr(request.user, 'parent'):
                if student.parent_guardian != request.user.parent:
                    return Response(
                        {'error': 'You do not have permission to set stream preference for this student'},
                        status=status.HTTP_403_FORBIDDEN
                    )

        # Update preference
        student.preferred_stream = preferred_stream
        student.save()

        return Response({
            'message': 'Stream preference updated successfully',
            'student_id': student.id,
            'student_name': student.full_name,
            'preferred_stream': student.preferred_stream
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, IsAdminUser])
    def pending(self, request):
        """
        List students who need stream assignment (have preference but not assigned).

        Returns:
        {
            "total_pending": 12,
            "students": [
                {
                    "student_id": 123,
                    "student_name": "John Doe",
                    "admission_number": "STD/2020/001",
                    "preferred_stream": "science",
                    "assigned_stream": null
                },
                ...
            ]
        }
        """
        # Find students with preferred_stream but no assigned_stream
        pending_students = Student.objects.filter(
            preferred_stream__isnull=False,
            assigned_stream__isnull=True,
            is_active=True
        ).values(
            'id',
            'first_name',
            'middle_name',
            'last_name',
            'admission_number',
            'preferred_stream',
            'assigned_stream'
        )

        students_list = []
        for student in pending_students:
            students_list.append({
                'student_id': student['id'],
                'student_name': f"{student['first_name']} {student['middle_name'] or ''} {student['last_name']}".strip(),
                'admission_number': student['admission_number'],
                'preferred_stream': student['preferred_stream'],
                'assigned_stream': student['assigned_stream']
            })

        return Response({
            'total_pending': len(students_list),
            'students': students_list
        }, status=status.HTTP_200_OK)


class StudentEnrollmentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for student classroom enrollments.

    Endpoints:
    - GET /api/academic/enrollments/ - List all enrollments
    - GET /api/academic/enrollments/{id}/ - Get specific enrollment
    - GET /api/academic/enrollments/student/{student_id}/history/ - Student's enrollment history
    - GET /api/academic/enrollments/academic-year/{year_id}/ - Enrollments for academic year
    """
    queryset = StudentClassEnrollment.objects.all()
    serializer_class = StudentClassEnrollmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter queryset based on user permissions"""
        queryset = StudentClassEnrollment.objects.select_related(
            'student',
            'classroom',
            'academic_year'
        ).order_by('-academic_year__start_date', 'student__admission_number')

        # Filter by academic year if provided
        academic_year_id = self.request.query_params.get('academic_year_id')
        if academic_year_id:
            queryset = queryset.filter(academic_year_id=academic_year_id)

        # Filter by active status
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        # Parents can only see their children's enrollments
        if not self.request.user.is_staff and hasattr(self.request.user, 'parent'):
            parent = self.request.user.parent
            queryset = queryset.filter(student__parent_guardian=parent)

        return queryset

    @action(detail=False, methods=['get'], url_path='student/(?P<student_id>[^/.]+)/history')
    def student_history(self, request, student_id=None):
        """
        Get enrollment history for a specific student.

        Returns all enrollments ordered by academic year (most recent first).
        """
        try:
            student = Student.objects.get(id=student_id)
        except Student.DoesNotExist:
            return Response(
                {'error': f'Student {student_id} not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check permissions
        if not request.user.is_staff:
            if hasattr(request.user, 'parent'):
                if student.parent_guardian != request.user.parent:
                    return Response(
                        {'error': 'You do not have permission to view this student\'s enrollment history'},
                        status=status.HTTP_403_FORBIDDEN
                    )

        enrollments = StudentClassEnrollment.objects.filter(
            student=student
        ).select_related(
            'classroom',
            'academic_year'
        ).order_by('-academic_year__start_date')

        serializer = self.get_serializer(enrollments, many=True)

        return Response({
            'student_id': student.id,
            'student_name': student.full_name,
            'admission_number': student.admission_number,
            'total_enrollments': enrollments.count(),
            'enrollments': serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='academic-year/(?P<year_id>[^/.]+)')
    def by_academic_year(self, request, year_id=None):
        """
        Get all enrollments for a specific academic year.

        Includes summary statistics.
        """
        try:
            academic_year = AcademicYear.objects.get(id=year_id)
        except AcademicYear.DoesNotExist:
            return Response(
                {'error': f'Academic year {year_id} not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        enrollments = self.get_queryset().filter(academic_year=academic_year)
        serializer = self.get_serializer(enrollments, many=True)

        # Calculate statistics
        stats = {
            'total_enrollments': enrollments.count(),
            'active_enrollments': enrollments.filter(is_active=True).count(),
            'unique_students': enrollments.values('student').distinct().count(),
            'unique_classrooms': enrollments.values('classroom').distinct().count(),
        }

        return Response({
            'academic_year_id': academic_year.id,
            'academic_year_name': str(academic_year),
            'statistics': stats,
            'enrollments': serializer.data
        }, status=status.HTTP_200_OK)
