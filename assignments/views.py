"""
Assignment Views - Phase 1.7: Assignment & Homework Management

Provides viewsets for:
- Teachers: Create/manage assignments, grade submissions
- Students: View assignments, submit work
- Parents: View children's assignments and grades
"""
import logging
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Q, Count, Avg, Prefetch

from .models import (
    Assignment,
    AssignmentAttachment,
    AssignmentSubmission,
    SubmissionAttachment,
    AssignmentGrade
)
from .serializers import (
    AssignmentSerializer,
    AssignmentCreateSerializer,
    AssignmentAttachmentSerializer,
    AssignmentSubmissionSerializer,
    AssignmentSubmissionCreateSerializer,
    SubmissionAttachmentSerializer,
    AssignmentGradeSerializer,
    AssignmentGradeCreateSerializer,
    AssignmentSummarySerializer,
    StudentAssignmentSerializer
)
from academic.models import Student, Teacher
from academic.permissions import IsStudentOwner, IsParentOfStudent, IsStudentOrParent
from .permissions import IsTeacher

logger = logging.getLogger(__name__)


class TeacherAssignmentViewSet(viewsets.ModelViewSet):
    """
    Teacher assignment management:
    - Create/update/delete assignments
    - Upload attachments
    - View submissions
    - Grade student work
    """
    permission_classes = [IsAuthenticated, IsTeacher]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'description', 'classroom__name', 'subject__name']
    ordering_fields = ['assigned_date', 'due_date', 'created_at']
    ordering = ['-assigned_date']
    
    def get_queryset(self):
        """Return assignments created by this teacher"""
        teacher = get_object_or_404(Teacher, user=self.request.user)
        
        queryset = Assignment.objects.filter(teacher=teacher).select_related(
            'teacher', 'classroom', 'subject', 'academic_year', 'term'
        ).prefetch_related('attachments')
        
        # Filter by status
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by classroom
        classroom_id = self.request.query_params.get('classroom', None)
        if classroom_id:
            queryset = queryset.filter(classroom_id=classroom_id)
        
        # Filter by subject
        subject_id = self.request.query_params.get('subject', None)
        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)
        
        # Filter by term
        term_id = self.request.query_params.get('term', None)
        if term_id:
            queryset = queryset.filter(term_id=term_id)
        
        return queryset
    
    def get_serializer_class(self):
        if self.action == 'create':
            return AssignmentCreateSerializer
        elif self.action == 'list':
            return AssignmentSummarySerializer
        return AssignmentSerializer
    
    def perform_create(self, serializer):
        """Automatically set teacher when creating assignment"""
        teacher = get_object_or_404(Teacher, user=self.request.user)
        serializer.save(teacher=teacher, assigned_date=timezone.now())
    
    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload_attachment(self, request, pk=None):
        """Upload teacher attachment to assignment"""
        assignment = self.get_object()
        
        file = request.FILES.get('file')
        if not file:
            return Response(
                {'error': 'No file provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        attachment = AssignmentAttachment.objects.create(
            assignment=assignment,
            file=file
        )
        
        serializer = AssignmentAttachmentSerializer(attachment, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['delete'])
    def delete_attachment(self, request, pk=None):
        """Delete assignment attachment"""
        assignment = self.get_object()
        attachment_id = request.data.get('attachment_id')
        
        if not attachment_id:
            return Response(
                {'error': 'attachment_id required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        attachment = get_object_or_404(
            AssignmentAttachment,
            id=attachment_id,
            assignment=assignment
        )
        attachment.delete()
        
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['get'])
    def submissions(self, request, pk=None):
        """Get all submissions for this assignment"""
        assignment = self.get_object()
        
        submissions = AssignmentSubmission.objects.filter(
            assignment=assignment
        ).select_related(
            'student', 'student__parent_guardian'
        ).prefetch_related(
            'attachments', 'grade'
        ).order_by('-submitted_at')
        
        # Filter by graded status
        graded_filter = request.query_params.get('graded', None)
        if graded_filter == 'true':
            submissions = submissions.filter(grade__isnull=False)
        elif graded_filter == 'false':
            submissions = submissions.filter(grade__isnull=True)
        
        # Filter by late status
        late_filter = request.query_params.get('late', None)
        if late_filter == 'true':
            submissions = submissions.filter(is_late=True)
        elif late_filter == 'false':
            submissions = submissions.filter(is_late=False)
        
        serializer = AssignmentSubmissionSerializer(
            submissions,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def grade_submission(self, request, pk=None):
        """Grade a student's submission"""
        assignment = self.get_object()
        teacher = get_object_or_404(Teacher, user=request.user)
        
        submission_id = request.data.get('submission_id')
        if not submission_id:
            return Response(
                {'error': 'submission_id required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        submission = get_object_or_404(
            AssignmentSubmission,
            id=submission_id,
            assignment=assignment
        )
        
        # Check if already graded
        if hasattr(submission, 'grade'):
            return Response(
                {'error': 'Submission already graded. Use update endpoint to modify grade.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = AssignmentGradeCreateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(graded_by=teacher)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['put', 'patch'])
    def update_grade(self, request, pk=None):
        """Update an existing grade"""
        assignment = self.get_object()
        
        submission_id = request.data.get('submission_id')
        if not submission_id:
            return Response(
                {'error': 'submission_id required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        submission = get_object_or_404(
            AssignmentSubmission,
            id=submission_id,
            assignment=assignment
        )
        
        if not hasattr(submission, 'grade'):
            return Response(
                {'error': 'Submission not yet graded. Use grade_submission endpoint.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        grade = submission.grade
        serializer = AssignmentGradeCreateSerializer(
            grade,
            data=request.data,
            partial=True
        )
        
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        """Get assignment statistics"""
        assignment = self.get_object()
        
        submissions = assignment.submissions.all()
        graded = submissions.filter(grade__isnull=False)
        
        stats = {
            'total_students': assignment.total_students,
            'submission_count': assignment.submission_count,
            'submission_rate': assignment.submission_rate,
            'graded_count': assignment.graded_count,
            'pending_grading': assignment.submission_count - assignment.graded_count,
            'late_submissions': submissions.filter(is_late=True).count(),
            'on_time_submissions': submissions.filter(is_late=False).count(),
            'average_score': graded.aggregate(Avg('grade__score'))['grade__score__avg'] or 0,
            'is_overdue': assignment.is_overdue,
        }
        
        return Response(stats)


class StudentAssignmentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Student assignment view:
    - View published assignments
    - Submit work
    - View own submissions and grades
    """
    permission_classes = [IsAuthenticated, IsStudentOwner]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'subject__name']
    ordering_fields = ['assigned_date', 'due_date']
    ordering = ['-assigned_date']
    
    def get_queryset(self):
        """Return published assignments for student's classroom"""
        student = get_object_or_404(Student, user=self.request.user)
        
        # Get student's current classroom enrollment
        from academic.models import StudentClassEnrollment
        current_enrollment = StudentClassEnrollment.objects.filter(
            student=student,
            is_active=True
        ).select_related('classroom').first()
        
        if not current_enrollment:
            return Assignment.objects.none()
        
        queryset = Assignment.objects.filter(
            classroom=current_enrollment.classroom,
            status='published',
            is_active=True
        ).select_related(
            'teacher', 'classroom', 'subject', 'academic_year', 'term'
        ).prefetch_related('attachments')
        
        # Filter by subject
        subject_id = self.request.query_params.get('subject', None)
        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)
        
        # Filter by submission status
        submitted_filter = self.request.query_params.get('submitted', None)
        if submitted_filter == 'true':
            queryset = queryset.filter(submissions__student=student)
        elif submitted_filter == 'false':
            queryset = queryset.exclude(submissions__student=student)
        
        return queryset
    
    def get_serializer_class(self):
        return AssignmentSerializer
    
    def list(self, request, *args, **kwargs):
        """Return assignments with student-specific data"""
        queryset = self.filter_queryset(self.get_queryset())
        student = get_object_or_404(Student, user=request.user)
        
        assignments_data = []
        for assignment in queryset:
            # Get student's submission if exists
            submission = assignment.submissions.filter(student=student).first()
            
            assignment_dict = {
                'id': assignment.id,
                'title': assignment.title,
                'description': assignment.description,
                'assignment_type': assignment.assignment_type,
                'subject_name': assignment.subject.name,
                'teacher_name': assignment.teacher.user.get_full_name() if assignment.teacher.user else 'Unknown',
                'due_date': assignment.due_date,
                'max_score': assignment.max_score,
                'is_overdue': assignment.is_overdue,
                'has_submitted': submission is not None,
                'submission_id': submission.id if submission else None,
                'is_graded': hasattr(submission, 'grade') if submission else False,
                'grade': None,
                'attachments': AssignmentAttachmentSerializer(
                    assignment.attachments.all(),
                    many=True,
                    context={'request': request}
                ).data
            }
            
            # Add grade data if graded
            if submission and hasattr(submission, 'grade'):
                grade = submission.grade
                assignment_dict['grade'] = {
                    'score': float(grade.score),
                    'final_score': float(grade.final_score),
                    'percentage': grade.percentage,
                    'grade_letter': grade.grade_letter,
                    'feedback': grade.feedback,
                    'late_penalty_applied': float(grade.late_penalty_applied),
                    'graded_at': grade.graded_at
                }
            
            assignments_data.append(assignment_dict)
        
        serializer = StudentAssignmentSerializer(assignments_data, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def submit(self, request, pk=None):
        """Submit assignment"""
        assignment = self.get_object()
        student = get_object_or_404(Student, user=request.user)
        
        # Check if already submitted
        existing_submission = AssignmentSubmission.objects.filter(
            assignment=assignment,
            student=student
        ).first()
        
        if existing_submission:
            return Response(
                {'error': 'You have already submitted this assignment. Use update endpoint to modify.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if late submission is allowed
        if timezone.now() > assignment.due_date and not assignment.allow_late_submission:
            return Response(
                {'error': 'Late submissions are not allowed for this assignment.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        submission_text = request.data.get('submission_text', '')
        
        submission = AssignmentSubmission.objects.create(
            assignment=assignment,
            student=student,
            submission_text=submission_text
        )
        
        # Handle file uploads
        files = request.FILES.getlist('files')
        for file in files:
            SubmissionAttachment.objects.create(
                submission=submission,
                file=file
            )
        
        serializer = AssignmentSubmissionSerializer(submission, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['put', 'patch'], parser_classes=[MultiPartParser, FormParser])
    def update_submission(self, request, pk=None):
        """Update existing submission (before graded)"""
        assignment = self.get_object()
        student = get_object_or_404(Student, user=request.user)
        
        submission = get_object_or_404(
            AssignmentSubmission,
            assignment=assignment,
            student=student
        )
        
        # Check if already graded
        if hasattr(submission, 'grade'):
            return Response(
                {'error': 'Cannot update submission after it has been graded.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update submission text if provided
        submission_text = request.data.get('submission_text')
        if submission_text is not None:
            submission.submission_text = submission_text
            submission.save()
        
        # Handle new file uploads
        files = request.FILES.getlist('files')
        for file in files:
            SubmissionAttachment.objects.create(
                submission=submission,
                file=file
            )
        
        serializer = AssignmentSubmissionSerializer(submission, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def my_submission(self, request, pk=None):
        """Get student's own submission for this assignment"""
        assignment = self.get_object()
        student = get_object_or_404(Student, user=request.user)
        
        submission = AssignmentSubmission.objects.filter(
            assignment=assignment,
            student=student
        ).prefetch_related('attachments', 'grade').first()
        
        if not submission:
            return Response(
                {'detail': 'No submission found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = AssignmentSubmissionSerializer(submission, context={'request': request})
        return Response(serializer.data)


class ParentAssignmentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Parent view of children's assignments:
    - View all assignments for children
    - View submissions and grades
    - Track progress
    """
    permission_classes = [IsAuthenticated, IsParentOfStudent]
    serializer_class = AssignmentSerializer
    
    def get_queryset(self):
        """Return assignments for all parent's children"""
        from academic.models import Parent
        parent = get_object_or_404(Parent, user=self.request.user)
        
        # Get all active children
        children = parent.students.filter(is_active=True)
        
        # Get classrooms of all children
        from academic.models import StudentClassEnrollment
        classrooms = StudentClassEnrollment.objects.filter(
            student__in=children,
            is_active=True
        ).values_list('classroom', flat=True)
        
        queryset = Assignment.objects.filter(
            classroom__in=classrooms,
            status='published',
            is_active=True
        ).select_related(
            'teacher', 'classroom', 'subject', 'academic_year', 'term'
        ).prefetch_related('attachments').distinct()
        
        # Filter by child
        child_id = self.request.query_params.get('child', None)
        if child_id:
            child = get_object_or_404(Student, id=child_id, parent_guardian=parent)
            child_classroom = StudentClassEnrollment.objects.filter(
                student=child,
                is_active=True
            ).values_list('classroom', flat=True).first()
            
            if child_classroom:
                queryset = queryset.filter(classroom=child_classroom)
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def children_overview(self, request):
        """Get assignment overview for all children"""
        from academic.models import Parent
        parent = get_object_or_404(Parent, user=request.user)
        
        children = parent.students.filter(is_active=True)
        overview = []
        
        for child in children:
            from academic.models import StudentClassEnrollment
            current_enrollment = StudentClassEnrollment.objects.filter(
                student=child,
                is_active=True
            ).first()
            
            if not current_enrollment:
                continue
            
            assignments = Assignment.objects.filter(
                classroom=current_enrollment.classroom,
                status='published',
                is_active=True
            )
            
            total_assignments = assignments.count()
            submissions = AssignmentSubmission.objects.filter(
                student=child,
                assignment__in=assignments
            )
            
            submitted_count = submissions.count()
            graded_count = submissions.filter(grade__isnull=False).count()
            pending_count = total_assignments - submitted_count
            
            # Upcoming assignments (due within 7 days, not submitted)
            upcoming = assignments.filter(
                due_date__gte=timezone.now(),
                due_date__lte=timezone.now() + timezone.timedelta(days=7)
            ).exclude(
                submissions__student=child
            ).count()
            
            # Overdue assignments (not submitted)
            overdue = assignments.filter(
                due_date__lt=timezone.now()
            ).exclude(
                submissions__student=child
            ).count()
            
            overview.append({
                'student_id': child.id,
                'student_name': child.full_name,
                'classroom': str(current_enrollment.classroom),
                'total_assignments': total_assignments,
                'submitted': submitted_count,
                'graded': graded_count,
                'pending': pending_count,
                'upcoming': upcoming,
                'overdue': overdue
            })
        
        return Response(overview)
    
    @action(detail=True, methods=['get'])
    def child_submission(self, request, pk=None):
        """View a specific child's submission"""
        assignment = self.get_object()
        
        child_id = request.query_params.get('child_id')
        if not child_id:
            return Response(
                {'error': 'child_id query parameter required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from academic.models import Parent
        parent = get_object_or_404(Parent, user=request.user)
        
        child = get_object_or_404(
            Student,
            id=child_id,
            parent_guardian=parent
        )
        
        submission = AssignmentSubmission.objects.filter(
            assignment=assignment,
            student=child
        ).prefetch_related('attachments', 'grade').first()
        
        if not submission:
            return Response(
                {'detail': 'No submission found for this child'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = AssignmentSubmissionSerializer(submission, context={'request': request})
        return Response(serializer.data)
