"""
Public API endpoints for admission portal.
No authentication required - for external applicants.
"""

from rest_framework import mixins, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from core.email_utils import (
    send_admission_confirmation_email,
    send_admission_accepted_email,
    get_school_settings,
    send_email,
)

from academic.models import (
    AdmissionSession,
    AdmissionFeeStructure,
    AdmissionApplication,
    AdmissionDocument,
    AdmissionStatus,
    ClassLevel,
)
from academic.serializers import (
    ClassLevelSerializer,
    AdmissionSessionPublicSerializer,
    AdmissionFeeStructurePublicSerializer,
    AdmissionApplicationCreateSerializer,
    AdmissionApplicationUpdateSerializer,
    AdmissionApplicationDetailSerializer,
    PublicAdmissionApplicationSerializer,
    AdmissionDocumentSerializer,
    PublicAdmissionDocumentSerializer,
    PublicAdmissionDocumentUploadSerializer,
    ApplicationTrackingSerializer,
)


class PublicAdmissionSessionViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    Public endpoint to view active admission session.

    GET /api/public/admissions/session/ - Get active session info
    """
    permission_classes = [AllowAny]
    serializer_class = AdmissionSessionPublicSerializer

    def get_queryset(self):
        """Only return active, open sessions"""
        today = timezone.localdate()
        return AdmissionSession.objects.filter(
            is_active=True,
            allow_public_applications=True,
            start_date__lte=today,
            end_date__gte=today,
        )

    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get the currently active admission session"""
        session = self.get_queryset().first()

        if not session:
            return Response({
                'active': False,
                'message': 'No active admission session available at this time.',
                'session': None
            }, status=status.HTTP_200_OK)

        serializer = self.get_serializer(session)
        return Response({
            'active': True,
            'message': 'Admission session is currently open',
            'session': serializer.data
        })


class PublicAdmissionFeeStructureViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    Public endpoint to view admission fees for different classes.

    GET /api/public/admissions/fee-structures/ - List fees for all classes
    GET /api/public/admissions/fee-structures/{id}/ - Fee details for specific class
    """
    permission_classes = [AllowAny]
    serializer_class = AdmissionFeeStructurePublicSerializer

    def get_queryset(self):
        """Only return fee structures for active session"""
        today = timezone.localdate()
        active_session = AdmissionSession.objects.filter(
            is_active=True,
            allow_public_applications=True,
            start_date__lte=today,
            end_date__gte=today,
        ).first()

        if not active_session:
            return AdmissionFeeStructure.objects.none()

        return AdmissionFeeStructure.objects.filter(
            admission_session=active_session
        ).select_related('admission_session').prefetch_related('grade_levels')


class PublicAdmissionApplicationViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    Public endpoint for application submission and tracking.

    POST   /api/public/admissions/applications/ - Submit new application
    GET    /api/public/admissions/applications/track/ - Track application
    PATCH  /api/public/admissions/applications/{token}/ - Update draft application
    POST   /api/public/admissions/applications/{token}/submit/ - Submit draft
    POST   /api/public/admissions/applications/{token}/accept/ - Accept offer
    """
    permission_classes = [AllowAny]
    lookup_field = 'tracking_token'

    def get_serializer_class(self):
        if self.action == 'create':
            return AdmissionApplicationCreateSerializer
        elif self.action == 'partial_update':
            return AdmissionApplicationUpdateSerializer
        return PublicAdmissionApplicationSerializer

    def get_queryset(self):
        """Allow access only via tracking token"""
        return AdmissionApplication.objects.select_related(
            'admission_session',
            'applying_for_class',
            'reviewed_by',
            'enrolled_student'
        ).prefetch_related(
            'documents',
            'assessments'
        )

    def create(self, request, *args, **kwargs):
        """
        Create new application (starts as DRAFT).

        Request body should include all student and parent information.
        Returns application with tracking token.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Create application in DRAFT status
        application = serializer.save(status=AdmissionStatus.DRAFT)

        # Return full details including tracking token
        detail_serializer = PublicAdmissionApplicationSerializer(
            application,
            context={'request': request}
        )

        return Response({
            'message': 'Application created successfully. Save your tracking token to check status later.',
            'application': detail_serializer.data,
            'tracking_token': application.tracking_token,
            'application_number': application.application_number,
        }, status=status.HTTP_201_CREATED)

    def retrieve(self, request, tracking_token=None):
        """
        Get application details using tracking token.

        No authentication required - anyone with the token can view.
        """
        application = get_object_or_404(
            self.get_queryset(),
            tracking_token=tracking_token
        )

        serializer = self.get_serializer(application)
        return Response(serializer.data)

    def partial_update(self, request, tracking_token=None):
        """
        Update application (only allowed for DRAFT applications).

        Parents can update their draft application before submitting.
        """
        application = get_object_or_404(
            self.get_queryset(),
            tracking_token=tracking_token
        )

        # Only allow updates for draft applications
        if application.status != AdmissionStatus.DRAFT:
            return Response({
                'error': 'Only draft applications can be updated. This application has been submitted.'
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(
            application,
            data=request.data,
            partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # Return full details
        detail_serializer = PublicAdmissionApplicationSerializer(
            application,
            context={'request': request}
        )

        return Response({
            'message': 'Application updated successfully.',
            'application': detail_serializer.data
        })

    @action(detail=False, methods=['post'])
    def track(self, request):
        """
        Track application status using application number and email/phone.

        POST /api/public/admissions/applications/track/
        Body: {
            "application_number": "ADM/2025/001",
            "email": "parent@example.com"  (or "phone": "08012345678")
        }
        """
        application_number = request.data.get('application_number')
        email = request.data.get('email')
        phone = request.data.get('phone')

        if not application_number:
            return Response({
                'error': 'Application number is required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        if not email and not phone:
            return Response({
                'error': 'Email or phone number is required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Find application
        query = Q(application_number=application_number)
        if email:
            query &= Q(parent_email__iexact=email)
        if phone:
            query &= Q(parent_phone=phone)

        application = self.get_queryset().filter(query).first()

        if not application:
            return Response({
                'error': 'Application not found. Please check your details.'
            }, status=status.HTTP_404_NOT_FOUND)

        # Return tracking information
        serializer = ApplicationTrackingSerializer({
            'application_number': application.application_number,
            'status': application.status,
            'status_display': application.get_status_display(),
            'applicant_name': application.full_name,
            'applying_for_class': str(application.applying_for_class),
            'submitted_at': application.submitted_at,
            'application_fee_paid': application.application_fee_paid,
            'exam_fee_paid': application.exam_fee_paid,
            'acceptance_fee_paid': application.acceptance_fee_paid,
            'acceptance_deadline': application.acceptance_deadline,
            'next_steps': self._get_next_steps(application),
        })

        return Response({
            'tracking_token': application.tracking_token,
            'application': serializer.data
        })

    def get_throttles(self):
        if self.action == 'track':
            self.throttle_scope = 'public_admission_track'
            return [ScopedRateThrottle()]
        return super().get_throttles()

    @action(detail=True, methods=['post'])
    def submit(self, request, tracking_token=None):
        """
        Submit application (DRAFT → SUBMITTED).

        POST /api/public/admissions/applications/{token}/submit/

        Validates that application can be submitted and changes status.
        """
        application = get_object_or_404(
            self.get_queryset(),
            tracking_token=tracking_token
        )

        # Only allow submission of draft applications
        if application.status != AdmissionStatus.DRAFT:
            return Response({
                'error': f'Application has already been submitted. Current status: {application.get_status_display()}'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check if application can be submitted
        if not application.can_submit:
            return Response({
                'error': 'Application fee must be paid before submission.',
                'fee_required': True
            }, status=status.HTTP_400_BAD_REQUEST)

        # Submit application
        application.status = AdmissionStatus.SUBMITTED
        application.submitted_at = timezone.now()
        application.save()

        transaction.on_commit(lambda: self._send_submission_notifications(application))

        serializer = PublicAdmissionApplicationSerializer(
            application,
            context={'request': request}
        )

        return Response({
            'message': 'Application submitted successfully! You will receive updates via email.',
            'application': serializer.data
        })

    @action(detail=True, methods=['post'])
    def accept_offer(self, request, tracking_token=None):
        """
        Accept admission offer (APPROVED → ACCEPTED).

        POST /api/public/admissions/applications/{token}/accept/

        Parent accepts the admission offer after approval.
        Requires acceptance fee payment if configured.
        """
        application = get_object_or_404(
            self.get_queryset(),
            tracking_token=tracking_token
        )

        # Only allow acceptance of approved applications
        if application.status != AdmissionStatus.APPROVED:
            return Response({
                'error': f'Application must be approved before acceptance. Current status: {application.get_status_display()}'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check if acceptance deadline has passed
        if application.acceptance_deadline and timezone.now() > application.acceptance_deadline:
            return Response({
                'error': 'Acceptance deadline has passed. Please contact the school.',
                'deadline': application.acceptance_deadline
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check if application can be accepted
        if not application.can_accept_offer:
            return Response({
                'error': 'Acceptance fee must be paid before accepting offer.',
                'fee_required': True,
                'acceptance_deadline': application.acceptance_deadline
            }, status=status.HTTP_400_BAD_REQUEST)

        # Accept offer
        application.status = AdmissionStatus.ACCEPTED
        application.accepted_at = timezone.now()
        application.save()

        transaction.on_commit(lambda: self._send_acceptance_notifications(application))

        serializer = PublicAdmissionApplicationSerializer(
            application,
            context={'request': request}
        )

        return Response({
            'message': 'Congratulations! You have accepted the admission offer. You will receive enrollment instructions via email.',
            'application': serializer.data
        })

    @action(detail=True, methods=['get'])
    def payment_info(self, request, tracking_token=None):
        """
        Get payment information for application.

        GET /api/public/admissions/applications/{token}/payment/

        Returns what fees need to be paid and payment instructions.
        """
        application = get_object_or_404(
            self.get_queryset(),
            tracking_token=tracking_token
        )

        fee_structure = AdmissionFeeStructure.objects.filter(
            admission_session=application.admission_session,
            grade_levels=application.applying_for_class,
        ).first()

        if not fee_structure:
            return Response({
                'error': 'Fee structure not configured for this class.'
            }, status=status.HTTP_404_NOT_FOUND)

        payment_info = {
            'application_number': application.application_number,
            'applicant_name': application.full_name,
            'class': str(application.applying_for_class),
            'fees': []
        }

        # Application fee
        if fee_structure.application_fee > 0:
            payment_info['fees'].append({
                'type': 'application',
                'name': 'Application Fee',
                'amount': float(fee_structure.application_fee),
                'currency': 'NGN',
                'required': fee_structure.application_fee_required,
                'paid': application.application_fee_paid,
                'payment_date': application.application_fee_payment_date,
            })

        # Exam fee
        if fee_structure.entrance_exam_fee > 0 and fee_structure.entrance_exam_required:
            payment_info['fees'].append({
                'type': 'exam',
                'name': 'Entrance Examination Fee',
                'amount': float(fee_structure.entrance_exam_fee),
                'currency': 'NGN',
                'required': fee_structure.entrance_exam_required,
                'paid': application.exam_fee_paid,
                'payment_date': application.exam_fee_payment_date,
            })

        # Acceptance fee
        if fee_structure.acceptance_fee > 0:
            payment_info['fees'].append({
                'type': 'acceptance',
                'name': 'Acceptance Fee',
                'amount': float(fee_structure.acceptance_fee),
                'currency': 'NGN',
                'required': fee_structure.acceptance_fee_required,
                'paid': application.acceptance_fee_paid,
                'payment_date': application.acceptance_fee_payment_date,
                'is_part_of_tuition': fee_structure.acceptance_fee_is_part_of_tuition,
                'deadline': application.acceptance_deadline,
            })

        # Calculate totals
        total_required = sum(
            fee['amount'] for fee in payment_info['fees']
            if fee['required'] and not fee['paid']
        )
        total_paid = sum(
            fee['amount'] for fee in payment_info['fees']
            if fee['paid']
        )

        payment_info['total_required'] = total_required
        payment_info['total_paid'] = total_paid
        payment_info['balance'] = total_required

        # Payment instructions — pulled from school settings where available
        school = get_school_settings()
        payment_info['payment_instructions'] = {
            'bank_name': fee_structure.bank_name if hasattr(fee_structure, 'bank_name') and fee_structure.bank_name else 'Contact school for bank details',
            'account_number': fee_structure.account_number if hasattr(fee_structure, 'account_number') and fee_structure.account_number else 'Contact school',
            'account_name': school.get('school_name', 'School Account'),
            'reference': application.application_number,
            'note': 'Please use your application number as payment reference.',
            'contact_email': school.get('contact_email') or '',
            'contact_phone': school.get('contact_phone') or '',
        }

        return Response(payment_info)

    @staticmethod
    def _notification_context(application):
        return {
            'student_name': application.full_name,
            'application_number': application.application_number,
            'class_level': str(application.applying_for_class),
            'parent_name': f"{application.parent_first_name} {application.parent_last_name}".strip(),
            'parent_email': application.parent_email,
            'parent_phone': application.parent_phone,
        }

    @classmethod
    def _send_admin_notification(cls, application, subject):
        try:
            admin_email = get_school_settings().get('contact_email')
            if admin_email:
                send_email(
                    subject=subject,
                    to_email=admin_email,
                    template_name='admin_new_registration',
                    context=cls._notification_context(application),
                    fail_silently=True,
                )
        except Exception:
            pass

    @classmethod
    def _send_submission_notifications(cls, application):
        try:
            send_admission_confirmation_email(application)
        except Exception:
            pass
        cls._send_admin_notification(
            application, f"New Admission Application — {application.application_number}"
        )

    @classmethod
    def _send_acceptance_notifications(cls, application):
        try:
            send_admission_accepted_email(application)
        except Exception:
            pass
        cls._send_admin_notification(
            application, f"Offer Accepted — {application.application_number}"
        )

    def _get_next_steps(self, application):
        """Get human-readable next steps for applicant"""
        if application.status == AdmissionStatus.DRAFT:
            if application.can_submit:
                return "Complete and submit your application."
            return "Pay application fee to submit application."

        elif application.status == AdmissionStatus.SUBMITTED:
            return "Your application is being reviewed. You will be notified of the next steps."

        elif application.status == AdmissionStatus.UNDER_REVIEW:
            return "Your application is under review. Check back for updates."

        elif application.status == AdmissionStatus.DOCUMENTS_PENDING:
            return "Please upload the required documents."

        elif application.status == AdmissionStatus.EXAM_SCHEDULED:
            return "Your entrance examination has been scheduled. Check your email for details."

        elif application.status == AdmissionStatus.EXAM_COMPLETED:
            return "Your examination results are being processed."

        elif application.status == AdmissionStatus.INTERVIEW_SCHEDULED:
            return "Your interview has been scheduled. Check your email for details."

        elif application.status == AdmissionStatus.APPROVED:
            if application.can_accept_offer:
                return "Congratulations! Click 'Accept Offer' to confirm your enrollment."
            return "Pay acceptance fee to accept your admission offer."

        elif application.status == AdmissionStatus.ACCEPTED:
            return "Your enrollment is being processed. You will receive confirmation soon."

        elif application.status == AdmissionStatus.ENROLLED:
            return "You have been successfully enrolled! Welcome to the school."

        elif application.status == AdmissionStatus.REJECTED:
            return "Your application was not successful. You may apply again in the next session."

        elif application.status == AdmissionStatus.WITHDRAWN:
            return "This application has been withdrawn."

        return "Check your email for updates."


class PublicAdmissionDocumentViewSet(viewsets.GenericViewSet):
    """
    Public endpoint for document uploads.

    GET    /api/public/admissions/applications/{token}/documents/ - List documents
    POST   /api/public/admissions/applications/{token}/documents/ - Upload document
    DELETE /api/public/admissions/documents/{id}/ - Delete document (before verification)
    """
    permission_classes = [AllowAny]
    serializer_class = PublicAdmissionDocumentSerializer

    def get_serializer_class(self):
        if self.action == 'create':
            return PublicAdmissionDocumentUploadSerializer
        return PublicAdmissionDocumentSerializer

    def get_queryset(self):
        """Filter documents by application tracking token"""
        tracking_token = self.kwargs.get('tracking_token')
        if tracking_token:
            return AdmissionDocument.objects.filter(
                application__tracking_token=tracking_token
            ).select_related('application', 'verified_by')
        return AdmissionDocument.objects.none()

    def list(self, request, tracking_token=None):
        """List all documents for an application"""
        application = get_object_or_404(
            AdmissionApplication,
            tracking_token=tracking_token
        )

        documents = self.get_queryset()
        serializer = self.get_serializer(documents, many=True)

        return Response({
            'application_number': application.application_number,
            'documents': serializer.data
        })

    def create(self, request, tracking_token=None):
        """Upload a document for application"""
        application = get_object_or_404(
            AdmissionApplication,
            tracking_token=tracking_token
        )

        # Check if application allows document uploads
        if application.status not in [
            AdmissionStatus.DRAFT,
            AdmissionStatus.SUBMITTED,
            AdmissionStatus.UNDER_REVIEW,
            AdmissionStatus.DOCUMENTS_PENDING
        ]:
            return Response({
                'error': 'Document uploads are no longer allowed for this application.'
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = serializer.save(application=application)
        transaction.on_commit(lambda: PublicAdmissionApplicationViewSet._send_admin_notification(
            application, f"New Document Uploaded — {application.application_number}"
        ))

        response_serializer = PublicAdmissionDocumentSerializer(
            document, context=self.get_serializer_context()
        )

        return Response({
            'message': 'Document uploaded successfully.',
            'document': response_serializer.data
        }, status=status.HTTP_201_CREATED)

    def destroy(self, request, tracking_token=None, document_public_id=None):
        """Delete a document (only if not yet verified)"""
        application = get_object_or_404(
            AdmissionApplication, tracking_token=tracking_token
        )
        document = get_object_or_404(
            AdmissionDocument,
            application=application,
            public_id=document_public_id,
        )

        # Only allow deletion of unverified documents
        if document.verified:
            return Response({
                'error': 'Cannot delete verified documents. Please contact the school.'
            }, status=status.HTTP_400_BAD_REQUEST)

        document.delete()

        return Response({
            'message': 'Document deleted successfully.'
        }, status=status.HTTP_204_NO_CONTENT)


class PublicClassLevelViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    Public endpoint to view available classes for application.

    GET /api/public/admissions/classes/ - List available classes
    """
    permission_classes = [AllowAny]
    queryset = ClassLevel.objects.none()
    serializer_class = ClassLevelSerializer

    def list(self, request):
        """List classes available for admission in active session"""
        today = timezone.localdate()
        active_session = AdmissionSession.objects.filter(
            is_active=True,
            allow_public_applications=True,
            start_date__lte=today,
            end_date__gte=today,
        ).first()

        if not active_session:
            return Response({
                'error': 'No active admission session available.'
            }, status=status.HTTP_404_NOT_FOUND)

        # Get classes with fee structures configured
        fee_structures = AdmissionFeeStructure.objects.filter(
            admission_session=active_session
        ).prefetch_related('grade_levels')

        classes = []
        included_grade_ids = set()
        for fee_structure in fee_structures:
            for grade_level in fee_structure.grade_levels.all():
                if grade_level.pk in included_grade_ids:
                    continue
                included_grade_ids.add(grade_level.pk)
                classes.append({
                    'id': grade_level.id,
                    'name': str(grade_level),
                    'application_fee': float(fee_structure.application_fee),
                    'entrance_exam_required': fee_structure.entrance_exam_required,
                    'interview_required': fee_structure.interview_required,
                    'has_capacity': fee_structure.has_capacity,
                })

        return Response({
            'session': active_session.name,
            'classes': classes
        })
