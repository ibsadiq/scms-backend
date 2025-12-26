"""
Admin API views for admission management.
Requires authentication and appropriate permissions.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta

from .models import (
    AdmissionSession,
    AdmissionFeeStructure,
    AdmissionApplication,
    AdmissionDocument,
    AdmissionAssessment,
    AssessmentTemplate,
    AssessmentCriterion,
    AssessmentTemplateCriterion,
)
from .serializers_admission import (
    AdmissionSessionSerializer,
    AdmissionFeeStructureSerializer,
    AdmissionApplicationListSerializer,
    AdmissionApplicationDetailSerializer,
    AdmissionApplicationUpdateSerializer,
    AdmissionDocumentSerializer,
    AdmissionAssessmentDetailSerializer,
    AdmissionAssessmentCreateSerializer,
    AssessmentTemplateDetailSerializer,
    AssessmentCriterionSerializer,
)


class AdmissionSessionAdminViewSet(viewsets.ModelViewSet):
    """
    Admin endpoint for managing admission sessions.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    queryset = AdmissionSession.objects.all().order_by('-start_date')
    serializer_class = AdmissionSessionSerializer

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """
        Activate this session and deactivate all others.
        """
        session = self.get_object()

        # Deactivate all other sessions
        AdmissionSession.objects.exclude(pk=session.pk).update(is_active=False)

        # Activate this session
        session.is_active = True
        session.save()

        serializer = self.get_serializer(session)
        return Response({
            'message': 'Session activated successfully',
            'admission_session': serializer.data
        })

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """
        Deactivate this session.
        """
        session = self.get_object()
        session.is_active = False
        session.save()

        serializer = self.get_serializer(session)
        return Response({
            'message': 'Session deactivated successfully',
            'admission_session': serializer.data
        })

    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        """
        Get statistics for this admission session.
        """
        session = self.get_object()

        applications = AdmissionApplication.objects.filter(session=session)

        stats = {
            'total_applications': applications.count(),
            'by_status': {
                'draft': applications.filter(status='DRAFT').count(),
                'submitted': applications.filter(status='SUBMITTED').count(),
                'under_review': applications.filter(status='UNDER_REVIEW').count(),
                'documents_pending': applications.filter(status='DOCUMENTS_PENDING').count(),
                'exam_scheduled': applications.filter(status='EXAM_SCHEDULED').count(),
                'exam_completed': applications.filter(status='EXAM_COMPLETED').count(),
                'interview_scheduled': applications.filter(status='INTERVIEW_SCHEDULED').count(),
                'approved': applications.filter(status='APPROVED').count(),
                'rejected': applications.filter(status='REJECTED').count(),
                'accepted': applications.filter(status='ACCEPTED').count(),
                'enrolled': applications.filter(status='ENROLLED').count(),
                'withdrawn': applications.filter(status='WITHDRAWN').count(),
            },
            'by_class': {},
            'pending_actions': {
                'new_submissions': applications.filter(status='SUBMITTED').count(),
                'pending_documents': applications.filter(status='DOCUMENTS_PENDING').count(),
                'pending_exams': applications.filter(status='EXAM_SCHEDULED').count(),
                'pending_interviews': applications.filter(status='INTERVIEW_SCHEDULED').count(),
                'awaiting_acceptance': applications.filter(status='APPROVED').count(),
            },
            'revenue': {
                'application_fees': applications.filter(application_fee_paid=True).count(),
                'exam_fees': applications.filter(exam_fee_paid=True).count(),
                'acceptance_fees': applications.filter(acceptance_fee_paid=True).count(),
            }
        }

        # By class level
        class_counts = applications.values('applying_for_class__name').annotate(
            count=Count('id')
        ).order_by('-count')

        for item in class_counts:
            stats['by_class'][item['applying_for_class__name']] = item['count']

        return Response(stats)


class AdmissionFeeStructureAdminViewSet(viewsets.ModelViewSet):
    """
    Admin endpoint for managing admission fee structures.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = AdmissionFeeStructureSerializer
    queryset = AdmissionFeeStructure.objects.all().select_related(
        'admission_session', 'class_room'
    ).order_by('-admission_session__start_date', 'class_room__name')

    def get_queryset(self):
        queryset = super().get_queryset()
        session_id = self.request.query_params.get('admission_session')

        if session_id:
            queryset = queryset.filter(admission_session_id=session_id)

        return queryset


class AdmissionApplicationAdminViewSet(viewsets.ModelViewSet):
    """
    Admin endpoint for managing admission applications.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    queryset = AdmissionApplication.objects.all().select_related(
        'admission_session', 'applying_for_class', 'enrolled_student', 'reviewed_by'
    ).prefetch_related('documents', 'assessments').order_by('-created_at')

    def get_serializer_class(self):
        if self.action == 'list':
            return AdmissionApplicationListSerializer
        elif self.action in ['update', 'partial_update']:
            return AdmissionApplicationUpdateSerializer
        return AdmissionApplicationDetailSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by session
        session_id = self.request.query_params.get('admission_session')
        if session_id:
            queryset = queryset.filter(session_id=session_id)

        # Filter by status
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)

        # Filter by class level
        applying_for_class_id = self.request.query_params.get('class_level')
        if applying_for_class_id:
            queryset = queryset.filter(applying_for_class_id=applying_for_class_id)

        # Search by name, email, phone, or application number
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search) |
                Q(phone_number__icontains=search) |
                Q(application_number__icontains=search)
            )

        # Filter by payment status
        payment_status = self.request.query_params.get('payment_status')
        if payment_status == 'paid':
            queryset = queryset.filter(application_fee_paid=True)
        elif payment_status == 'unpaid':
            queryset = queryset.filter(application_fee_paid=False)

        # Filter by pending actions
        pending_action = self.request.query_params.get('pending_action')
        if pending_action == 'new_submissions':
            queryset = queryset.filter(status='SUBMITTED')
        elif pending_action == 'pending_documents':
            queryset = queryset.filter(status='DOCUMENTS_PENDING')
        elif pending_action == 'pending_exams':
            queryset = queryset.filter(status='EXAM_SCHEDULED')
        elif pending_action == 'pending_interviews':
            queryset = queryset.filter(status='INTERVIEW_SCHEDULED')
        elif pending_action == 'awaiting_acceptance':
            queryset = queryset.filter(status='APPROVED')

        return queryset

    @action(detail=False, methods=['get'], url_path='dashboard-stats')
    def dashboard_stats(self, request):
        """
        Get aggregated statistics for admission dashboard.
        Returns stats for the active session or all applications.
        """
        # Get active session or all applications
        active_session = AdmissionSession.objects.filter(is_active=True).first()

        if active_session:
            applications = AdmissionApplication.objects.filter(session=active_session)
        else:
            applications = AdmissionApplication.objects.all()

        # Count by status
        total_applications = applications.count()
        pending_review = applications.filter(
            status__in=['SUBMITTED', 'UNDER_REVIEW', 'DOCUMENTS_PENDING']
        ).count()
        approved = applications.filter(status='APPROVED').count()
        enrolled = applications.filter(status='ENROLLED').count()

        # Calculate revenue
        application_revenue = sum(
            app.session.fee_structures.filter(
                class_room=app.applying_for_class
            ).first().application_fee or 0
            for app in applications.filter(application_fee_paid=True)
            if app.session.fee_structures.filter(class_room=app.applying_for_class).exists()
        )

        exam_revenue = sum(
            app.session.fee_structures.filter(
                class_room=app.applying_for_class
            ).first().entrance_exam_fee or 0
            for app in applications.filter(exam_fee_paid=True)
            if app.session.fee_structures.filter(class_room=app.applying_for_class).exists()
        )

        acceptance_revenue = sum(
            app.session.fee_structures.filter(
                class_room=app.applying_for_class
            ).first().acceptance_fee or 0
            for app in applications.filter(acceptance_fee_paid=True)
            if app.session.fee_structures.filter(class_room=app.applying_for_class).exists()
        )

        return Response({
            'total_applications': total_applications,
            'pending_review': pending_review,
            'approved': approved,
            'enrolled': enrolled,
            'application_revenue': application_revenue,
            'exam_revenue': exam_revenue,
            'acceptance_revenue': acceptance_revenue,
            'active_session': active_session.name if active_session else None,
        })

    @action(detail=True, methods=['post'])
    def start_review(self, request, pk=None):
        """
        Move application from SUBMITTED to UNDER_REVIEW.
        """
        application = self.get_object()

        if application.status != 'SUBMITTED':
            return Response(
                {'error': 'Application must be in SUBMITTED status'},
                status=status.HTTP_400_BAD_REQUEST
            )

        application.status = 'UNDER_REVIEW'
        application.reviewed_by = request.user
        application.reviewed_at = timezone.now()
        application.save()

        serializer = self.get_serializer(application)
        return Response({
            'message': 'Application review started',
            'application': serializer.data
        })

    @action(detail=True, methods=['post'])
    def request_documents(self, request, pk=None):
        """
        Move application to DOCUMENTS_PENDING.
        """
        application = self.get_object()

        if application.status not in ['SUBMITTED', 'UNDER_REVIEW']:
            return Response(
                {'error': 'Invalid status for requesting documents'},
                status=status.HTTP_400_BAD_REQUEST
            )

        notes = request.data.get('notes', '')

        application.status = 'DOCUMENTS_PENDING'
        application.admin_notes = notes
        application.save()

        # TODO: Send email to parent requesting documents

        serializer = self.get_serializer(application)
        return Response({
            'message': 'Document request sent',
            'application': serializer.data
        })

    @action(detail=True, methods=['post'])
    def schedule_exam(self, request, pk=None):
        """
        Schedule entrance exam for application.
        """
        application = self.get_object()

        if application.status not in ['UNDER_REVIEW', 'DOCUMENTS_PENDING']:
            return Response(
                {'error': 'Invalid status for scheduling exam'},
                status=status.HTTP_400_BAD_REQUEST
            )

        exam_date = request.data.get('exam_date')
        exam_time = request.data.get('exam_time')
        exam_venue = request.data.get('exam_venue')

        if not all([exam_date, exam_time, exam_venue]):
            return Response(
                {'error': 'exam_date, exam_time, and exam_venue are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        application.status = 'EXAM_SCHEDULED'
        application.exam_date = exam_date
        application.exam_time = exam_time
        application.exam_venue = exam_venue
        application.save()

        # TODO: Send email to parent with exam details

        serializer = self.get_serializer(application)
        return Response({
            'message': 'Exam scheduled successfully',
            'application': serializer.data
        })

    @action(detail=True, methods=['post'])
    def mark_exam_completed(self, request, pk=None):
        """
        Mark exam as completed.
        """
        application = self.get_object()

        if application.status != 'EXAM_SCHEDULED':
            return Response(
                {'error': 'Application must be in EXAM_SCHEDULED status'},
                status=status.HTTP_400_BAD_REQUEST
            )

        application.status = 'EXAM_COMPLETED'
        application.save()

        serializer = self.get_serializer(application)
        return Response({
            'message': 'Exam marked as completed',
            'application': serializer.data
        })

    @action(detail=True, methods=['post'])
    def schedule_interview(self, request, pk=None):
        """
        Schedule interview for application.
        """
        application = self.get_object()

        if application.status not in ['UNDER_REVIEW', 'EXAM_COMPLETED']:
            return Response(
                {'error': 'Invalid status for scheduling interview'},
                status=status.HTTP_400_BAD_REQUEST
            )

        interview_date = request.data.get('interview_date')
        interview_time = request.data.get('interview_time')
        interview_venue = request.data.get('interview_venue')

        if not all([interview_date, interview_time, interview_venue]):
            return Response(
                {'error': 'interview_date, interview_time, and interview_venue are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        application.status = 'INTERVIEW_SCHEDULED'
        application.interview_date = interview_date
        application.interview_time = interview_time
        application.interview_venue = interview_venue
        application.save()

        # TODO: Send email to parent with interview details

        serializer = self.get_serializer(application)
        return Response({
            'message': 'Interview scheduled successfully',
            'application': serializer.data
        })

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """
        Approve application and send admission offer.
        """
        application = self.get_object()

        if application.status in ['APPROVED', 'ACCEPTED', 'ENROLLED']:
            return Response(
                {'error': 'Application is already approved/accepted/enrolled'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if application.status in ['REJECTED', 'WITHDRAWN']:
            return Response(
                {'error': 'Cannot approve rejected or withdrawn application'},
                status=status.HTTP_400_BAD_REQUEST
            )

        approval_notes = request.data.get('approval_notes', '')

        application.status = 'APPROVED'
        application.approved_by = request.user
        application.approved_at = timezone.now()
        application.approval_notes = approval_notes

        # Calculate offer expiry date
        if application.admission_session.offer_expiry_days:
            application.offer_expiry_date = timezone.now().date() + timedelta(
                days=application.admission_session.offer_expiry_days
            )

        application.save()

        # TODO: Send admission offer email to parent

        serializer = self.get_serializer(application)
        return Response({
            'message': 'Application approved successfully',
            'application': serializer.data
        })

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """
        Reject application.
        """
        application = self.get_object()

        if application.status in ['ACCEPTED', 'ENROLLED']:
            return Response(
                {'error': 'Cannot reject accepted or enrolled application'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if application.status == 'REJECTED':
            return Response(
                {'error': 'Application is already rejected'},
                status=status.HTTP_400_BAD_REQUEST
            )

        rejection_reason = request.data.get('rejection_reason', '')

        if not rejection_reason:
            return Response(
                {'error': 'rejection_reason is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        application.status = 'REJECTED'
        application.approved_by = request.user
        application.approved_at = timezone.now()
        application.rejection_reason = rejection_reason
        application.save()

        # TODO: Send rejection email to parent

        serializer = self.get_serializer(application)
        return Response({
            'message': 'Application rejected',
            'application': serializer.data
        })

    @action(detail=True, methods=['post'])
    def enroll(self, request, pk=None):
        """
        Enroll student from ACCEPTED application.
        This creates a Student record and enrolls them in the class.
        """
        application = self.get_object()

        if application.status != 'ACCEPTED':
            return Response(
                {'error': 'Application must be in ACCEPTED status'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if application.student:
            return Response(
                {'error': 'Student already enrolled'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create Student record
        from .models import Student
        from users.models import CustomUser

        # Check if user already exists with this email
        user = None
        if application.email:
            user = CustomUser.objects.filter(email=application.email).first()

        # Create new user if doesn't exist
        if not user:
            user = CustomUser.objects.create_user(
                username=application.email or f"student_{application.application_number}",
                email=application.email,
                first_name=application.first_name,
                last_name=application.last_name,
                is_student=True
            )
            # Set a default password (should be changed on first login)
            user.set_password('ChangeMe123!')
            user.save()

        # Create Student record
        student = Student.objects.create(
            user=user,
            first_name=application.first_name,
            last_name=application.last_name,
            other_names=application.other_names,
            date_of_birth=application.date_of_birth,
            gender=application.gender,
            blood_group=application.blood_group,
            state_of_origin=application.state_of_origin,
            lga_of_origin=application.lga_of_origin,
            religion=application.religion,
            home_address=application.home_address,
            # Contact info
            email=application.email,
            phone_number=application.phone_number,
            alternative_contact=application.alternative_contact,
            # Previous school info
            previous_school=application.previous_school,
            previous_class=application.previous_class,
            # Medical info
            medical_conditions=application.medical_conditions,
            allergies=application.allergies,
            # Parent info
            parent_guardian_name=application.parent_guardian_name,
            parent_guardian_relationship=application.parent_guardian_relationship,
            parent_guardian_phone=application.parent_guardian_phone,
            parent_guardian_email=application.parent_guardian_email,
            parent_guardian_address=application.parent_guardian_address,
            parent_guardian_occupation=application.parent_guardian_occupation,
        )

        # Enroll in class
        from .models import StudentClassEnrollment
        from administration.models import AcademicYear

        # Get current academic year
        current_year = AcademicYear.objects.filter(is_current=True).first()

        if current_year:
            StudentClassEnrollment.objects.create(
                student=student,
                class_room=application.applying_for_class.class_room if hasattr(application.class_level, 'class_room') else None,
                academic_year=current_year,
                enrollment_date=timezone.now().date()
            )

        # Update application
        application.status = 'ENROLLED'
        application.enrolled_student = student
        application.save()

        # TODO: Send welcome email with login credentials

        serializer = self.get_serializer(application)
        return Response({
            'message': 'Student enrolled successfully',
            'application': serializer.data,
            'student_id': student.id,
            'username': user.username
        })

    @action(detail=True, methods=['post'])
    def withdraw(self, request, pk=None):
        """
        Withdraw application (can be done by admin or parent).
        """
        application = self.get_object()

        if application.status in ['ENROLLED', 'REJECTED']:
            return Response(
                {'error': 'Cannot withdraw enrolled or rejected application'},
                status=status.HTTP_400_BAD_REQUEST
            )

        withdrawal_reason = request.data.get('withdrawal_reason', '')

        application.status = 'WITHDRAWN'
        application.admin_notes = withdrawal_reason
        application.save()

        serializer = self.get_serializer(application)
        return Response({
            'message': 'Application withdrawn',
            'application': serializer.data
        })

    @action(detail=False, methods=['get'])
    def export(self, request):
        """
        Export applications to CSV.
        """
        import csv
        from django.http import HttpResponse

        queryset = self.filter_queryset(self.get_queryset())

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="applications.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Application Number', 'First Name', 'Last Name', 'Email', 'Phone',
            'Class Level', 'Status', 'Date of Birth', 'Gender',
            'Submitted At', 'Reviewed At', 'Approved At'
        ])

        for app in queryset:
            writer.writerow([
                app.application_number,
                app.first_name,
                app.last_name,
                app.email,
                app.phone_number,
                app.class_level.name,
                app.get_status_display(),
                app.date_of_birth,
                app.gender,
                app.submitted_at,
                app.reviewed_at,
                app.approved_at
            ])

        return response


class AdmissionDocumentAdminViewSet(viewsets.ModelViewSet):
    """
    Admin endpoint for managing admission documents.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = AdmissionDocumentSerializer
    queryset = AdmissionDocument.objects.all().select_related(
        'application', 'verified_by'
    ).order_by('-uploaded_at')

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by application
        application_id = self.request.query_params.get('application')
        if application_id:
            queryset = queryset.filter(application_id=application_id)

        # Filter by verification status
        verified = self.request.query_params.get('verified')
        if verified == 'true':
            queryset = queryset.filter(is_verified=True)
        elif verified == 'false':
            queryset = queryset.filter(is_verified=False)

        return queryset

    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        """
        Verify a document.
        """
        document = self.get_object()

        if document.is_verified:
            return Response(
                {'error': 'Document is already verified'},
                status=status.HTTP_400_BAD_REQUEST
            )

        verification_notes = request.data.get('verification_notes', '')

        document.is_verified = True
        document.verified_by = request.user
        document.verified_at = timezone.now()
        document.verification_notes = verification_notes
        document.save()

        # Check if all required documents are verified
        application = document.application
        all_verified = not application.documents.filter(
            is_required=True, is_verified=False
        ).exists()

        if all_verified and application.status == 'DOCUMENTS_PENDING':
            # Move application back to UNDER_REVIEW
            application.status = 'UNDER_REVIEW'
            application.save()

        serializer = self.get_serializer(document)
        return Response({
            'message': 'Document verified successfully',
            'document': serializer.data
        })

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """
        Reject a document.
        """
        document = self.get_object()

        rejection_reason = request.data.get('rejection_reason', '')

        if not rejection_reason:
            return Response(
                {'error': 'rejection_reason is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        document.is_verified = False
        document.verified_by = request.user
        document.verified_at = timezone.now()
        document.verification_notes = rejection_reason
        document.save()

        # TODO: Notify parent about rejected document

        serializer = self.get_serializer(document)
        return Response({
            'message': 'Document rejected',
            'document': serializer.data
        })


class AdmissionAssessmentAdminViewSet(viewsets.ModelViewSet):
    """
    Admin endpoint for managing admission assessments.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    queryset = AdmissionAssessment.objects.all().select_related(
        'application', 'template', 'assessor'
    ).prefetch_related('criteria').order_by('-completed_at')

    def get_serializer_class(self):
        if self.action == 'create':
            return AdmissionAssessmentCreateSerializer
        return AdmissionAssessmentDetailSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by application
        application_id = self.request.query_params.get('application')
        if application_id:
            queryset = queryset.filter(application_id=application_id)

        return queryset

    def perform_create(self, serializer):
        serializer.save(assessor=self.request.user)


class AssessmentTemplateAdminViewSet(viewsets.ModelViewSet):
    """
    Admin endpoint for managing assessment templates.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = AssessmentTemplateDetailSerializer
    queryset = AssessmentTemplate.objects.all().prefetch_related(
        'criteria'
    ).order_by('name')

    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        """
        Duplicate an assessment template.
        """
        template = self.get_object()

        # Create new template
        new_template = AssessmentTemplate.objects.create(
            name=f"{template.name} (Copy)",
            description=template.description,
            is_active=False
        )

        # Copy criteria
        for criterion in template.criteria.all():
            AssessmentTemplateCriterion.objects.create(
                template=new_template,
                criterion=criterion.criterion,
                max_score=criterion.max_score,
                weight=criterion.weight
            )

        serializer = self.get_serializer(new_template)
        return Response({
            'message': 'Template duplicated successfully',
            'template': serializer.data
        })


class AssessmentCriterionAdminViewSet(viewsets.ModelViewSet):
    """
    Admin endpoint for managing assessment criteria.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = AssessmentCriterionSerializer
    queryset = AssessmentCriterion.objects.all().order_by('name')
