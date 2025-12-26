"""
Teacher-Specific Views (Phase 1.3)
Handles teacher dashboard, marks entry, and result viewing for teachers.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Avg, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import datetime, date

from .models import MarksManagement, TermResult, SubjectResult, ExaminationListHandler
from .serializers import MarksListSerializer, MarksCreateSerializer
from .permissions import CanEnterMarks, CanViewResults, IsTeacherOrAdmin
from academic.models import AllocatedSubject, StudentClassEnrollment, ClassRoom
from administration.models import Term
from schedule.models import Period


class TeacherDashboardViewSet(viewsets.ViewSet):
    """
    Teacher dashboard providing overview of classes, students, and marks.

    Endpoints:
    - GET /api/examination/teacher/dashboard/ - Dashboard overview
    - GET /api/examination/teacher/my-classes/ - Teacher's allocated classes
    - GET /api/examination/teacher/my-subjects/ - Teacher's allocated subjects
    - GET /api/examination/teacher/my-students/ - Students in teacher's classes
    """
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]

    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        """
        Get teacher dashboard overview.

        Returns summary statistics for the logged-in teacher.
        """
        try:
            teacher = request.user.teacher
        except AttributeError:
            return Response(
                {'error': 'User is not associated with a teacher account'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get allocated subjects
        allocations = AllocatedSubject.objects.filter(
            teacher_name=teacher
        ).select_related('subject', 'class_room', 'class_room__name')

        # Get unique classrooms
        classrooms = allocations.values_list('class_room', flat=True).distinct()
        classroom_count = classrooms.count()

        # Get unique subjects
        subjects = allocations.values_list('subject', flat=True).distinct()
        subject_count = subjects.count()

        # Get total students across all classes
        total_students = StudentClassEnrollment.objects.filter(
            class_room__in=classrooms,
            student__is_active=True
        ).count()

        # Get marks entered by teacher
        marks_entered = MarksManagement.objects.filter(
            created_by=teacher
        ).count()

        # Get recent marks (last 10)
        recent_marks = MarksManagement.objects.filter(
            created_by=teacher
        ).select_related(
            'exam_name', 'subject', 'student__student'
        ).order_by('-date_time')[:10]

        recent_marks_data = []
        for mark in recent_marks:
            recent_marks_data.append({
                'id': mark.id,
                'exam': mark.exam_name.name,
                'subject': mark.subject.name,
                'student': mark.student.student.full_name if hasattr(mark.student, 'student') else 'Unknown',
                'score': mark.points_scored,
                'max_score': mark.exam_name.out_of,
                'date': mark.date_time
            })

        # Get allocations summary
        allocations_data = []
        for allocation in allocations:
            classroom_name = str(allocation.class_room) if allocation.class_room else 'Unknown'
            allocations_data.append({
                'id': allocation.id,
                'subject': allocation.subject.name,
                'classroom': classroom_name,
                'subject_code': allocation.subject.subject_code if hasattr(allocation.subject, 'subject_code') else None
            })

        # Get today's timetable (Phase 1.3 Enhancement)
        today = timezone.now()
        day_name = today.strftime('%A')  # e.g., 'Monday', 'Tuesday', etc.

        todays_periods = Period.objects.filter(
            teacher=teacher,
            day_of_week=day_name,
            is_active=True
        ).select_related(
            'classroom',
            'classroom__name',
            'classroom__stream',
            'subject',
            'subject__subject'
        ).order_by('start_time')

        # Format today's schedule
        todays_schedule = []
        current_time = today.time()

        for period in todays_periods:
            classroom_name = str(period.classroom) if period.classroom else 'Unknown'
            subject_name = period.subject.subject.name if period.subject and period.subject.subject else 'Unknown'

            # Determine if period is current, upcoming, or past
            period_status = 'upcoming'
            if current_time >= period.end_time:
                period_status = 'past'
            elif current_time >= period.start_time and current_time < period.end_time:
                period_status = 'current'

            todays_schedule.append({
                'id': period.id,
                'subject': subject_name,
                'classroom': classroom_name,
                'start_time': period.start_time.strftime('%H:%M'),
                'end_time': period.end_time.strftime('%H:%M'),
                'room_number': period.room_number,
                'status': period_status,
                'notes': period.notes
            })

        # Get next period (if any)
        next_period = None
        upcoming_periods = [p for p in todays_schedule if p['status'] == 'upcoming']
        if upcoming_periods:
            next_period = upcoming_periods[0]

        return Response({
            'teacher_name': teacher.full_name,
            'current_day': day_name,
            'current_time': current_time.strftime('%H:%M'),
            'summary': {
                'classrooms': classroom_count,
                'subjects': subject_count,
                'total_students': total_students,
                'marks_entered': marks_entered,
                'periods_today': len(todays_schedule)
            },
            'allocations': allocations_data,
            'recent_marks': recent_marks_data,
            'todays_schedule': todays_schedule,
            'next_period': next_period
        })

    @action(detail=False, methods=['get'])
    def my_classes(self, request):
        """
        Get all classrooms allocated to the teacher.
        """
        try:
            teacher = request.user.teacher
        except AttributeError:
            return Response(
                {'error': 'User is not associated with a teacher account'},
                status=status.HTTP_403_FORBIDDEN
            )

        allocations = AllocatedSubject.objects.filter(
            teacher_name=teacher
        ).select_related('class_room', 'class_room__name', 'class_room__stream').distinct()

        classrooms = {}
        for allocation in allocations:
            classroom = allocation.class_room
            if classroom.id not in classrooms:
                classroom_name = str(classroom.name.name) if classroom.name else 'Unknown'
                if classroom.stream:
                    classroom_name += f" {classroom.stream.name}"

                # Get student count
                student_count = StudentClassEnrollment.objects.filter(
                    class_room=classroom,
                    student__is_active=True
                ).count()

                classrooms[classroom.id] = {
                    'id': classroom.id,
                    'name': classroom_name,
                    'level': classroom.name.name if classroom.name else None,
                    'stream': classroom.stream.name if classroom.stream else None,
                    'student_count': student_count
                }

        return Response(list(classrooms.values()))

    @action(detail=False, methods=['get'])
    def my_subjects(self, request):
        """
        Get all subjects allocated to the teacher with classroom breakdown.
        """
        try:
            teacher = request.user.teacher
        except AttributeError:
            return Response(
                {'error': 'User is not associated with a teacher account'},
                status=status.HTTP_403_FORBIDDEN
            )

        allocations = AllocatedSubject.objects.filter(
            teacher_name=teacher
        ).select_related('subject', 'class_room')

        subjects_data = []
        for allocation in allocations:
            classroom_name = str(allocation.class_room) if allocation.class_room else 'Unknown'

            subjects_data.append({
                'allocation_id': allocation.id,
                'subject_id': allocation.subject.id,
                'subject_name': allocation.subject.name,
                'subject_code': allocation.subject.subject_code if hasattr(allocation.subject, 'subject_code') else None,
                'classroom_id': allocation.class_room.id if allocation.class_room else None,
                'classroom_name': classroom_name
            })

        return Response(subjects_data)

    @action(detail=False, methods=['get'])
    def my_timetable(self, request):
        """
        Get teacher's timetable for the week.

        Query params:
        - day: Filter by specific day (optional)
        """
        try:
            teacher = request.user.teacher
        except AttributeError:
            return Response(
                {'error': 'User is not associated with a teacher account'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get day filter if provided
        day_filter = request.query_params.get('day')

        # Build query
        query = Period.objects.filter(
            teacher=teacher,
            is_active=True
        ).select_related(
            'classroom',
            'classroom__name',
            'classroom__stream',
            'subject',
            'subject__subject'
        )

        if day_filter:
            query = query.filter(day_of_week=day_filter)

        periods = query.order_by('day_of_week', 'start_time')

        # Organize by day
        timetable = {}
        for period in periods:
            day = period.day_of_week
            if day not in timetable:
                timetable[day] = []

            classroom_name = str(period.classroom) if period.classroom else 'Unknown'
            subject_name = period.subject.subject.name if period.subject and period.subject.subject else 'Unknown'

            timetable[day].append({
                'id': period.id,
                'subject': subject_name,
                'classroom': classroom_name,
                'start_time': period.start_time.strftime('%H:%M'),
                'end_time': period.end_time.strftime('%H:%M'),
                'room_number': period.room_number,
                'notes': period.notes
            })

        return Response({
            'teacher': teacher.full_name,
            'timetable': timetable
        })

    @action(detail=False, methods=['get'])
    def my_students(self, request):
        """
        Get all students in teacher's allocated classrooms.

        Query params:
        - classroom_id: Filter by specific classroom
        """
        try:
            teacher = request.user.teacher
        except AttributeError:
            return Response(
                {'error': 'User is not associated with a teacher account'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get teacher's classrooms
        classroom_ids = AllocatedSubject.objects.filter(
            teacher_name=teacher
        ).values_list('class_room', flat=True).distinct()

        # Filter by specific classroom if requested
        classroom_id = request.query_params.get('classroom_id')
        if classroom_id:
            classroom_ids = [int(classroom_id)] if int(classroom_id) in classroom_ids else []

        # Get students
        enrollments = StudentClassEnrollment.objects.filter(
            class_room_id__in=classroom_ids,
            student__is_active=True
        ).select_related('student', 'class_room')

        students_data = []
        for enrollment in enrollments:
            students_data.append({
                'id': enrollment.student.id,
                'enrollment_id': enrollment.id,
                'name': enrollment.student.full_name,
                'admission_number': enrollment.student.admission_number,
                'classroom': str(enrollment.class_room) if enrollment.class_room else 'Unknown',
                'classroom_id': enrollment.class_room.id if enrollment.class_room else None
            })

        return Response(students_data)


class TeacherMarksViewSet(viewsets.ModelViewSet):
    """
    ViewSet for teachers to manage marks entry.

    Endpoints:
    - GET /api/examination/teacher/marks/ - List marks entered by teacher
    - POST /api/examination/teacher/marks/ - Create new mark entry
    - GET /api/examination/teacher/marks/{id}/ - Get mark details
    - PATCH /api/examination/teacher/marks/{id}/ - Update mark
    - DELETE /api/examination/teacher/marks/{id}/ - Delete mark
    - GET /api/examination/teacher/marks/by_classroom/ - Get marks by classroom
    - GET /api/examination/teacher/marks/by_subject/ - Get marks by subject
    - POST /api/examination/teacher/marks/bulk_entry/ - Bulk mark entry
    """
    permission_classes = [IsAuthenticated, CanEnterMarks]
    queryset = MarksManagement.objects.all()

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update', 'bulk_entry']:
            return MarksCreateSerializer
        return MarksListSerializer

    def get_queryset(self):
        """Filter marks to show only those entered by the logged-in teacher"""
        queryset = super().get_queryset()

        # Admins see all marks
        if self.request.user.is_superuser:
            return queryset

        # Teachers see only their marks
        try:
            teacher = self.request.user.teacher
            return queryset.filter(created_by=teacher)
        except AttributeError:
            return queryset.none()

    def perform_create(self, serializer):
        """Automatically set created_by to the logged-in teacher"""
        try:
            teacher = self.request.user.teacher
            serializer.save(created_by=teacher)
        except AttributeError:
            # If user doesn't have a teacher profile, try to use as is
            serializer.save()

    @action(detail=False, methods=['get'])
    def by_classroom(self, request):
        """
        Get marks filtered by classroom and optionally by exam.

        Query params:
        - classroom_id: ClassRoom ID (required)
        - exam_id: ExaminationListHandler ID (optional)
        - subject_id: Subject ID (optional)
        """
        classroom_id = request.query_params.get('classroom_id')
        exam_id = request.query_params.get('exam_id')
        subject_id = request.query_params.get('subject_id')

        if not classroom_id:
            return Response(
                {'error': 'classroom_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        queryset = self.get_queryset().filter(
            student__class_room_id=classroom_id
        )

        if exam_id:
            queryset = queryset.filter(exam_name_id=exam_id)

        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)

        queryset = queryset.select_related(
            'exam_name', 'subject', 'student__student', 'created_by'
        ).order_by('subject__name', 'student__student__first_name')

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_subject(self, request):
        """
        Get marks filtered by subject and exam.

        Query params:
        - subject_id: Subject ID (required)
        - exam_id: ExaminationListHandler ID (required)
        - classroom_id: ClassRoom ID (optional)
        """
        subject_id = request.query_params.get('subject_id')
        exam_id = request.query_params.get('exam_id')
        classroom_id = request.query_params.get('classroom_id')

        if not subject_id or not exam_id:
            return Response(
                {'error': 'subject_id and exam_id parameters are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        queryset = self.get_queryset().filter(
            subject_id=subject_id,
            exam_name_id=exam_id
        )

        if classroom_id:
            queryset = queryset.filter(student__class_room_id=classroom_id)

        queryset = queryset.select_related(
            'exam_name', 'subject', 'student__student'
        ).order_by('student__student__first_name')

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def bulk_entry(self, request):
        """
        Bulk mark entry for multiple students.

        Request body:
        {
            "exam_id": 1,
            "subject_id": 2,
            "marks": [
                {"student_enrollment_id": 5, "score": 85},
                {"student_enrollment_id": 6, "score": 92},
                ...
            ]
        }
        """
        exam_id = request.data.get('exam_id')
        subject_id = request.data.get('subject_id')
        marks = request.data.get('marks', [])

        if not exam_id or not subject_id or not marks:
            return Response(
                {'error': 'exam_id, subject_id, and marks array are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            teacher = request.user.teacher
        except AttributeError:
            return Response(
                {'error': 'User is not associated with a teacher account'},
                status=status.HTTP_403_FORBIDDEN
            )

        created_marks = []
        errors = []

        for mark_data in marks:
            student_enrollment_id = mark_data.get('student_enrollment_id')
            score = mark_data.get('score')

            if not student_enrollment_id or score is None:
                errors.append({
                    'student_enrollment_id': student_enrollment_id,
                    'error': 'Missing student_enrollment_id or score'
                })
                continue

            try:
                serializer = MarksCreateSerializer(data={
                    'exam_name': exam_id,
                    'subject': subject_id,
                    'student': student_enrollment_id,
                    'points_scored': score,
                    'created_by': teacher.id
                })

                if serializer.is_valid():
                    serializer.save()
                    created_marks.append(serializer.data)
                else:
                    errors.append({
                        'student_enrollment_id': student_enrollment_id,
                        'errors': serializer.errors
                    })
            except Exception as e:
                errors.append({
                    'student_enrollment_id': student_enrollment_id,
                    'error': str(e)
                })

        return Response({
            'message': 'Bulk entry completed',
            'summary': {
                'total': len(marks),
                'created': len(created_marks),
                'failed': len(errors)
            },
            'created_marks': created_marks,
            'errors': errors
        }, status=status.HTTP_201_CREATED if created_marks else status.HTTP_400_BAD_REQUEST)


class TeacherResultsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for teachers to view results for their allocated classes.

    Endpoints:
    - GET /api/examination/teacher/results/ - List results for teacher's classes
    - GET /api/examination/teacher/results/{id}/ - Get detailed result
    - GET /api/examination/teacher/results/by_classroom/ - Get classroom results
    - GET /api/examination/teacher/results/by_subject/ - Get subject-wise results
    """
    permission_classes = [IsAuthenticated, CanViewResults]
    queryset = TermResult.objects.all()

    def get_queryset(self):
        """Filter results to show only for teacher's allocated classrooms"""
        queryset = super().get_queryset()

        # Admins see all results
        if self.request.user.is_superuser:
            return queryset

        # Teachers see results for their allocated classrooms
        try:
            teacher = self.request.user.teacher
            classroom_ids = AllocatedSubject.objects.filter(
                teacher_name=teacher
            ).values_list('class_room', flat=True).distinct()

            return queryset.filter(classroom_id__in=classroom_ids)
        except AttributeError:
            return queryset.none()

    @action(detail=False, methods=['get'])
    def by_classroom(self, request):
        """
        Get results for a specific classroom and term.

        Query params:
        - classroom_id: ClassRoom ID (required)
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

        # Return simplified data
        results_data = []
        for result in queryset:
            results_data.append({
                'id': result.id,
                'student': result.student.full_name,
                'admission_number': result.student.admission_number,
                'average_percentage': result.average_percentage,
                'grade': result.grade,
                'gpa': result.gpa,
                'position': result.position_in_class,
                'total_students': result.total_students
            })

        return Response(results_data)

    @action(detail=False, methods=['get'])
    def by_subject(self, request):
        """
        Get subject results for teacher's allocated subject.

        Query params:
        - subject_id: Subject ID (required)
        - classroom_id: ClassRoom ID (required)
        - term_id: Term ID (required)
        """
        subject_id = request.query_params.get('subject_id')
        classroom_id = request.query_params.get('classroom_id')
        term_id = request.query_params.get('term_id')

        if not subject_id or not classroom_id or not term_id:
            return Response(
                {'error': 'subject_id, classroom_id, and term_id parameters are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get subject results
        subject_results = SubjectResult.objects.filter(
            subject_id=subject_id,
            term_result__classroom_id=classroom_id,
            term_result__term_id=term_id
        ).select_related('term_result__student').order_by('position_in_subject')

        results_data = []
        for result in subject_results:
            results_data.append({
                'id': result.id,
                'student': result.term_result.student.full_name,
                'admission_number': result.term_result.student.admission_number,
                'ca_score': result.ca_score,
                'exam_score': result.exam_score,
                'total_score': result.total_score,
                'percentage': result.percentage,
                'grade': result.grade,
                'position': result.position_in_subject,
                'class_average': result.class_average
            })

        return Response(results_data)
