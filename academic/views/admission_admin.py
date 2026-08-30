"""
Admin API views for admission management.
Requires authentication and appropriate permissions.
"""

from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from academic.permissions import IsSchoolAdmin
from django.db.models import Q, Count
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib import admin
from core.email_utils import (
    send_admission_documents_required_email,
    send_admission_approved_email,
    send_admission_rejected_email,
    send_email,
)

from academic.models import (
    AcademicYear,
    GradeLevel,
    AdmissionSession,
    AdmissionFeeStructure,
    AdmissionApplication,
    AdmissionDocument,
    AdmissionAssessment,
    AssessmentTemplate,
    AssessmentCriterion,
    AssessmentTemplateCriterion,
    ClassRoom,
    AdmissionStatus,
    AdmissionApplicationNumberPolicy
)
from academic.services import (
    AdmissionEnrollmentService,
    NumberingService
)

from academic.serializers import (
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
    StudentAdmissionNumberPolicySerializer,
    AdmissionApplicationNumberPolicySerializer,
)


class BaseNumberPolicyView(APIView):
    permission_classes = [IsSchoolAdmin]
    model = None
    serializer_class = None

    def get_policy(self):
        policy = self.model.objects.filter(is_active=True).first()
        if policy:
            return policy
        return self.model()

    def get(self, request):
        policy = self.get_policy()
        data = self.serializer_class(policy).data
        data["preview"] = self.get_preview(request)
        return Response(data)

    def patch(self, request):
        current = self.model.objects.filter(is_active=True).first()
        instance = current or self.model()
        serializer = self.serializer_class(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        policy = serializer.save(updated_by=request.user, is_active=True)
        data = self.serializer_class(policy).data
        data["preview"] = self.get_preview(request)
        return Response(data)


class StudentAdmissionNumberPolicyView(BaseNumberPolicyView):
    from academic.models import StudentAdmissionNumberPolicy
    model = StudentAdmissionNumberPolicy
    serializer_class = StudentAdmissionNumberPolicySerializer

    def get_preview(self, request):
        policy = self.get_policy()

        academic_year = (
            AcademicYear.objects
            .filter(active_year=True)
            .first()
        )

        if not academic_year:
            return None

        grade_level = None

        grade_level_id = request.query_params.get(
            "grade_level"
        )

        if grade_level_id:
            grade_level = (
                GradeLevel.objects
                .filter(pk=grade_level_id)
                .first()
            )

        if policy.uses_section and not grade_level:
            grade_level = (
                GradeLevel.objects
                .order_by("sequence_order")
                .first()
            )

        return NumberingService.preview(
            policy=policy,
            grade_level=grade_level,
            year=academic_year.start_date.year,
        )



class AdmissionApplicationNumberPolicyView(BaseNumberPolicyView):

    model = AdmissionApplicationNumberPolicy
    serializer_class = AdmissionApplicationNumberPolicySerializer

    def get_preview(self, request):
        policy = self.get_policy()

        session_id = request.query_params.get(
            "admission_session"
        )

        session = None

        if session_id:
            session = (
                AdmissionSession.objects
                .select_related("academic_year")
                .filter(pk=session_id)
                .first()
            )

        if not session:
            session = (
                AdmissionSession.objects
                .select_related("academic_year")
                .filter(is_active=True)
                .first()
            )

        if not session:
            return None

        grade_level = None

        grade_level_id = request.query_params.get(
            "grade_level"
        )

        if grade_level_id:
            grade_level = (
                GradeLevel.objects
                .filter(pk=grade_level_id)
                .first()
            )

        if policy.uses_section and not grade_level:
            grade_level = (
                GradeLevel.objects
                .order_by("sequence_order")
                .first()
            )

        return NumberingService.preview(
            policy=policy,
            grade_level=grade_level,
            year=session.academic_year.start_date.year,
        )


class AdmissionSessionAdminViewSet(viewsets.ModelViewSet):
    """
    Admin endpoint for managing admission sessions.
    """
    permission_classes = [IsSchoolAdmin]
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

        applications = AdmissionApplication.objects.filter(admission_session=session)

        stats = {
            'total_applications': applications.count(),
            'by_status': {
                choice: applications.filter(status=choice).count()
                for choice, _ in AdmissionStatus.choices
            },
            'by_class': {},
            'pending_actions': {
                'new_submissions': applications.filter(status=AdmissionStatus.SUBMITTED).count(),
                'pending_documents': applications.filter(status=AdmissionStatus.DOCUMENTS_PENDING).count(),
                'awaiting_acceptance': applications.filter(status=AdmissionStatus.APPROVED).count(),
            },
            'revenue': {
                'application_fees': applications.filter(application_fee_paid=True).count(),
                'exam_fees': applications.filter(exam_fee_paid=True).count(),
                'acceptance_fees': applications.filter(acceptance_fee_paid=True).count(),
            }
        }

        # By class level
        class_counts = applications.values('applying_for_class__default_name').annotate(
            count=Count('id')
        ).order_by('-count')

        for item in class_counts:
            stats['by_class'][item['applying_for_class__default_name']] = item['count']

        return Response(stats)


class AdmissionFeeStructureAdminViewSet(viewsets.ModelViewSet):
    """
    Admin endpoint for managing admission fee structures.
    """
    permission_classes = [IsSchoolAdmin]
    serializer_class = AdmissionFeeStructureSerializer
    queryset = AdmissionFeeStructure.objects.all().prefetch_related(
        'grade_levels'
    ).select_related(
        'admission_session'
    ).order_by('-admission_session__start_date', 'id')

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
    permission_classes = [IsSchoolAdmin]
    queryset = AdmissionApplication.objects.all().select_related(
        'admission_session', 'applying_for_class', 'enrolled_student', 'reviewed_by'
    ).prefetch_related('documents', 'assessments').order_by('-created_at')

    def get_serializer_class(self):
        if self.action == 'list':
            return AdmissionApplicationListSerializer
        elif self.action in ['update', 'partial_update']:
            return AdmissionApplicationUpdateSerializer
        return AdmissionApplicationDetailSerializer

    def create(self, request, *args, **kwargs):
        return Response(
            {"error": "Applications must be created through the public application workflow."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def destroy(self, request, *args, **kwargs):
        return Response(
            {"error": "Admission applications are retained as workflow records."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by session
        session_id = self.request.query_params.get('admission_session')
        if session_id:
            queryset = queryset.filter(admission_session_id=session_id)

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
                Q(parent_email__icontains=search) |
                Q(parent_phone__icontains=search) |
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
            queryset = queryset.filter(status=AdmissionStatus.SUBMITTED)
        elif pending_action == 'pending_documents':
            queryset = queryset.filter(status=AdmissionStatus.DOCUMENTS_PENDING)
        elif pending_action == 'awaiting_acceptance':
            queryset = queryset.filter(status=AdmissionStatus.APPROVED)

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
            applications = AdmissionApplication.objects.filter(admission_session=active_session)
        else:
            applications = AdmissionApplication.objects.all()

        # Count by status
        total_applications = applications.count()
        pending_review = applications.filter(
            status__in=[
                AdmissionStatus.SUBMITTED,
                AdmissionStatus.UNDER_REVIEW,
                AdmissionStatus.DOCUMENTS_PENDING,
            ]
        ).count()
        approved = applications.filter(status=AdmissionStatus.APPROVED).count()
        enrolled = applications.filter(status=AdmissionStatus.ENROLLED).count()

        # Calculate revenue
        application_revenue = sum(
            app.admission_session.fee_structures.filter(
                grade_levels=app.applying_for_class
            ).first().application_fee or 0
            for app in applications.filter(application_fee_paid=True)
            if app.admission_session.fee_structures.filter(grade_levels=app.applying_for_class).exists()
        )

        exam_revenue = sum(
            app.admission_session.fee_structures.filter(
                grade_levels=app.applying_for_class
            ).first().entrance_exam_fee or 0
            for app in applications.filter(exam_fee_paid=True)
            if app.admission_session.fee_structures.filter(grade_levels=app.applying_for_class).exists()
        )

        acceptance_revenue = sum(
            app.admission_session.fee_structures.filter(
                grade_levels=app.applying_for_class
            ).first().acceptance_fee or 0
            for app in applications.filter(acceptance_fee_paid=True)
            if app.admission_session.fee_structures.filter(grade_levels=app.applying_for_class).exists()
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

        if application.status != AdmissionStatus.SUBMITTED:
            return Response(
                {'error': 'Application must be in SUBMITTED status'},
                status=status.HTTP_400_BAD_REQUEST
            )

        application.status = AdmissionStatus.UNDER_REVIEW
        application.reviewed_by = request.user
        application.save(update_fields=("status", "reviewed_by", "updated_at"))

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

        if application.status not in [AdmissionStatus.SUBMITTED, AdmissionStatus.UNDER_REVIEW]:
            return Response(
                {'error': 'Invalid status for requesting documents'},
                status=status.HTTP_400_BAD_REQUEST
            )

        notes = request.data.get('notes', '')

        application.status = AdmissionStatus.DOCUMENTS_PENDING
        application.admin_notes = notes
        application.save(update_fields=("status", "admin_notes", "updated_at"))

        try:
            send_admission_documents_required_email(
                application,
                admin_notes=notes,
            )
        except Exception:
            pass

        serializer = self.get_serializer(application)
        return Response({
            'message': 'Document request sent',
            'application': serializer.data
        })

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """
        Approve application and send admission offer.
        """
        application = self.get_object()

        if application.status not in [
            AdmissionStatus.UNDER_REVIEW, AdmissionStatus.DOCUMENTS_PENDING,
        ]:
            return Response(
                {'error': 'Only an application under review can be approved'},
                status=status.HTTP_400_BAD_REQUEST
            )

        application.status = AdmissionStatus.APPROVED
        application.reviewed_by = request.user
        application.admin_notes = request.data.get('approval_notes', '')
        application.save(update_fields=(
            "status", "reviewed_by", "admin_notes", "approved_at",
            "acceptance_deadline", "updated_at",
        ))

        try:
            send_admission_approved_email(application)
        except Exception:
            pass

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

        if application.status not in [
            AdmissionStatus.SUBMITTED, AdmissionStatus.UNDER_REVIEW,
            AdmissionStatus.DOCUMENTS_PENDING,
        ]:
            return Response(
                {'error': 'Cannot reject accepted or enrolled application'},
                status=status.HTTP_400_BAD_REQUEST
            )

        rejection_reason = request.data.get('rejection_reason', '')

        if not rejection_reason:
            return Response(
                {'error': 'rejection_reason is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        application.status = AdmissionStatus.REJECTED
        application.reviewed_by = request.user
        application.rejection_reason = rejection_reason
        application.save(update_fields=(
            "status", "reviewed_by", "rejection_reason", "updated_at",
        ))

        try:
            send_admission_rejected_email(application)
        except Exception:
            pass

        serializer = self.get_serializer(application)
        return Response({
            'message': 'Application rejected',
            'application': serializer.data
        })

    @action(detail=True, methods=['post'])
    def enroll(self, request, pk=None):
        """Atomically convert an accepted application into an enrolled Student."""
        application = self.get_object()
        classroom = ClassRoom.objects.filter(pk=request.data.get("classroom")).first()
        if not classroom:
            return Response({"error": "A valid classroom is required."}, status=400)
        try:
            student = AdmissionEnrollmentService.enroll(
                application=application, classroom=classroom, actor=request.user,
            )
        except ValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else exc.messages
            return Response({"error": detail}, status=status.HTTP_400_BAD_REQUEST)

        application.refresh_from_db()

        serializer = self.get_serializer(application)
        return Response({
            'message': 'Student enrolled successfully',
            'application': serializer.data,
            'student_id': student.id,
        })

    @action(detail=True, methods=['post'])
    def withdraw(self, request, pk=None):
        """
        Withdraw application (can be done by admin or parent).
        """
        application = self.get_object()

        if application.status in [AdmissionStatus.ENROLLED, AdmissionStatus.REJECTED]:
            return Response(
                {'error': 'Cannot withdraw enrolled or rejected application'},
                status=status.HTTP_400_BAD_REQUEST
            )

        withdrawal_reason = request.data.get('withdrawal_reason', '')

        application.status = AdmissionStatus.WITHDRAWN
        application.admin_notes = withdrawal_reason
        application.save(update_fields=("status", "admin_notes", "updated_at"))

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
                app.parent_email,
                app.parent_phone,
                str(app.applying_for_class),
                app.get_status_display(),
                app.date_of_birth,
                app.gender,
                app.submitted_at,
                '',
                app.approved_at
            ])

        return response


class AdmissionDocumentAdminViewSet(viewsets.ModelViewSet):
    """
    Admin endpoint for managing admission documents.
    """
    permission_classes = [IsSchoolAdmin]
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
            queryset = queryset.filter(verified=True)
        elif verified == 'false':
            queryset = queryset.filter(verified=False)

        return queryset

    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        """
        Verify a document.
        """
        document = self.get_object()

        if document.verified:
            return Response(
                {'error': 'Document is already verified'},
                status=status.HTTP_400_BAD_REQUEST
            )

        verification_notes = request.data.get('verification_notes', '')

        document.verified = True
        document.verified_by = request.user
        document.verified_at = timezone.now()
        document.verification_notes = verification_notes
        document.save()

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

        document.verified = False
        document.verified_by = request.user
        document.verified_at = timezone.now()
        document.verification_notes = rejection_reason
        document.save()

        try:
            application = document.application
            if application.parent_email:
                send_email(
                    subject=f"Document Update — {application.application_number}",
                    to_email=application.parent_email,
                    template_name='admission_document_rejected',
                    context={
                        'parent_name': f"{application.parent_first_name} {application.parent_last_name}",
                        'student_name': f"{application.first_name} {application.last_name}",
                        'application_number': application.application_number,
                        'document_name': document.document_type,
                        'rejection_reason': rejection_reason,
                    },
                    fail_silently=True,
                )
        except Exception:
            pass

        serializer = self.get_serializer(document)
        return Response({
            'message': 'Document rejected',
            'document': serializer.data
        })


class AdmissionAssessmentAdminViewSet(viewsets.ModelViewSet):
    """
    Admin endpoint for managing admission assessments.
    """
    permission_classes = [IsSchoolAdmin]
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
    permission_classes = [IsSchoolAdmin]
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
    permission_classes = [IsSchoolAdmin]
    serializer_class = AssessmentCriterionSerializer
    queryset = AssessmentCriterion.objects.all().order_by('name')


class AdmissionFeeStructureInline(admin.TabularInline):
    """Inline for fee structures in admission session"""
    model = AdmissionFeeStructure
    extra = 1
    fields = [
        'grade_levels', 'application_fee', 'application_fee_required',
        'entrance_exam_required', 'entrance_exam_fee', 'entrance_exam_pass_score',
        'interview_required', 'acceptance_fee', 'acceptance_fee_required',
        'acceptance_fee_is_part_of_tuition', 'max_applications'
    ]
