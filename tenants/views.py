"""
Tenant API Views - Refactored with ViewSets
"""
from rest_framework import status, viewsets, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAdminUser
from django.db import connection, transaction
from django.db.models import Sum, Count
from django_tenants.utils import schema_context
from .services import TenantService, TenantCreationError
from rest_framework.views import APIView
from .serializers import (
    SchoolSignupSerializer,
    TenantListSerializer,
    TenantDetailSerializer,
    InspectorSerializer,
    InspectorCreateSerializer,
    InspectorUpdateSerializer,
)
from .models import Client, Domain, TenantStatus, Inspector

from django.conf import settings

import logging

logger = logging.getLogger(__name__)


class PublicTenantViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    """
    Public endpoints for school registration.
    POST /api/tenants/                     - Register a new school
    GET  /api/tenants/check-subdomain/     - Check subdomain availability
    """
    permission_classes = [AllowAny]
    serializer_class = SchoolSignupSerializer

    def create(self, request):
        if connection.schema_name != 'public':
            return Response(
                {'error': 'This endpoint is only available on the main domain'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response({'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Super admins creating tenants directly → auto-activate immediately.
            # Public self-registrations → always pending approval.
            is_super_admin = (
                request.user.is_authenticated
                and request.user.is_superuser
            )
            auto_activate = is_super_admin

            # Capture admin_phone so we can notify after creation
            admin_phone = serializer.validated_data.get('admin_phone') or None

            result = TenantService.create_tenant(
                school_name=serializer.validated_data['school_name'],
                subdomain=serializer.validated_data['subdomain'],
                admin_email=serializer.validated_data['admin_email'],
                admin_first_name=serializer.validated_data['admin_first_name'],
                admin_last_name=serializer.validated_data['admin_last_name'],
                admin_phone=admin_phone,
                contact_email=serializer.validated_data.get('contact_email') or None,
                contact_phone=serializer.validated_data.get('contact_phone') or None,
                enable_mobile=serializer.validated_data.get('enable_mobile', False),
                auto_activate=auto_activate,
            )

            # Send acknowledgement / notification emails only after tenant
            # creation completes successfully. Failures in email sending
            # should not prevent the API from returning success.
            try:
                if auto_activate:
                    TenantService._send_welcome_email(
                        email=serializer.validated_data['admin_email'],
                        first_name=serializer.validated_data['admin_first_name'],
                        school_name=result['tenant'].name,
                        domain=result['domain'].domain,
                        username=serializer.validated_data['admin_email'],
                        reset_url=result.get('reset_url'),
                        has_mobile=serializer.validated_data.get('enable_mobile', False),
                    )
                else:
                    TenantService._send_pending_approval_email(
                        email=serializer.validated_data['admin_email'],
                        first_name=serializer.validated_data['admin_first_name'],
                        school_name=result['tenant'].name,
                        domain=result['domain'].domain,
                    )
                    TenantService._notify_super_admin_new_registration(
                        tenant=result['tenant'],
                        admin_email=serializer.validated_data['admin_email'],
                        admin_phone=admin_phone,
                    )
            except Exception as e:
                logger.warning('Failed to send registration emails for %s: %s', serializer.validated_data['admin_email'], e)

            if auto_activate:
                return Response({
                    'success': True,
                    'message': f"School '{result['tenant'].name}' created and activated.",
                    'data': {
                        'school_name': result['tenant'].name,
                        'status':      'active',
                        'domain':      result['domain'].domain,
                    }
                }, status=status.HTTP_201_CREATED)

            return Response({
                'success': True,
                'message': 'Registration received! You will receive login credentials within 24 hours after approval.',
                'data': {
                    'school_name':        result['tenant'].name,
                    'status':             'pending_approval',
                    'estimated_approval': '24 hours',
                    'contact_email':      'support@ssync.online'
                }
            }, status=status.HTTP_201_CREATED)

        except TenantCreationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {'error': f'An unexpected error occurred: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'], url_path='check-subdomain')
    def check_subdomain(self, request):
        subdomain = request.query_params.get('subdomain')
        if not subdomain:
            return Response(
                {'error': 'Subdomain parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        from django.conf import settings
        full_domain  = f"{subdomain}.{settings.BASE_DOMAIN}"
        is_available = not Domain.objects.filter(domain=full_domain).exists()

        return Response({
            'subdomain':   subdomain,
            'available':   is_available,
            'full_domain': full_domain if is_available else None,
            'message':     'Available' if is_available else 'Already taken'
        })


class AdminTenantViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Super Admin Dashboard - Manage all tenants.
    Only accessible from public schema by admin users.

    GET  /api/admin/tenants/                    - List all schools
    GET  /api/admin/tenants/pending/            - List pending approvals
    GET  /api/admin/tenants/stats/              - Get overall statistics
    GET  /api/admin/tenants/{id}/               - Get school details
    POST /api/admin/tenants/{id}/approve/       - Approve pending registration
    POST /api/admin/tenants/{id}/reject/        - Reject registration
    POST /api/admin/tenants/{id}/suspend/       - Suspend a school
    POST /api/admin/tenants/{id}/activate/      - Activate a school
    POST /api/admin/tenants/{id}/enable-mobile/ - Enable mobile access
    POST /api/admin/tenants/{id}/disable-mobile/- Disable mobile access
    """
    permission_classes = [IsAdminUser]
    queryset = Client.objects.exclude(schema_name='public').order_by('-created_on')

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return TenantDetailSerializer
        return TenantListSerializer

    def _check_public_schema(self):
        if connection.schema_name != 'public':
            return Response(
                {'error': 'Super admin dashboard only available on main domain'},
                status=status.HTTP_403_FORBIDDEN
            )
        return None

    def list(self, request):
        """
        GET /api/admin/tenants/?status=active|pending|suspended|rejected
        """
        error_response = self._check_public_schema()
        if error_response:
            return error_response

        # Full unfiltered queryset for stats — always reflects all schools
        full_qs = self.get_queryset()

        # Filtered queryset for the table rows
        tenants = full_qs
        status_filter = request.query_params.get('status')
        if status_filter in TenantStatus.values:
            tenants = tenants.filter(status=status_filter)

        serializer = self.get_serializer(tenants, many=True)

        return Response({
            'count': tenants.count(),
            'stats': {
                'total':    full_qs.count(),
                'active':   full_qs.filter(status=TenantStatus.ACTIVE).count(),
                'pending':  full_qs.filter(status=TenantStatus.PENDING).count(),
                'premium':  full_qs.filter(has_mobile_access=True).count(),
                'standard': full_qs.filter(has_mobile_access=False).count(),
            },
            'tenants': serializer.data
        })

    @action(detail=False, methods=['get'])
    def pending(self, request):
        """GET /api/admin/tenants/pending/"""
        error_response = self._check_public_schema()
        if error_response:
            return error_response

        pending_tenants = self.get_queryset().filter(status=TenantStatus.PENDING)
        serializer = self.get_serializer(pending_tenants, many=True)

        return Response({
            'count':   pending_tenants.count(),
            'pending': serializer.data
        })

    def retrieve(self, request, pk=None):
        """GET /api/admin/tenants/{id}/"""
        error_response = self._check_public_schema()
        if error_response:
            return error_response

        tenant = self.get_object()
        return Response(self.get_serializer(tenant).data)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """GET /api/admin/tenants/stats/"""
        error_response = self._check_public_schema()
        if error_response:
            return error_response

        qs = self.get_queryset()

        agg = qs.aggregate(
            total_students=Sum('cached_student_count'),
            total_teachers=Sum('cached_teacher_count'),
        )

        by_status = {
            item['status']: item['count']
            for item in qs.values('status').annotate(count=Count('id'))
        }

        return Response({
            'total_schools':     qs.count(),
            'active_schools':    by_status.get(TenantStatus.ACTIVE,    0),
            'pending_schools':   by_status.get(TenantStatus.PENDING,   0),
            'suspended_schools': by_status.get(TenantStatus.SUSPENDED, 0),
            'rejected_schools':  by_status.get(TenantStatus.REJECTED,  0),
            'premium_schools':   qs.filter(has_mobile_access=True).count(),
            'standard_schools':  qs.filter(has_mobile_access=False).count(),
            'total_students':    agg['total_students'] or 0,
            'total_teachers':    agg['total_teachers'] or 0,
        })

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """POST /api/admin/tenants/{id}/approve/"""
        error_response = self._check_public_schema()   # ← was missing
        if error_response:
            return error_response

        try:
            with transaction.atomic():
                tenant = Client.objects.select_for_update().get(pk=pk)

                if tenant.status != TenantStatus.PENDING:
                    return Response(
                        {'error': 'Only pending schools can be approved'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                with schema_context(tenant.schema_name):
                    from django.contrib.auth import get_user_model
                    User   = get_user_model()
                    admin  = User.objects.filter(is_admin=True).first()

                    if not admin:
                        raise ValueError('No admin user found in tenant schema')

                    domain = tenant.domains.filter(is_primary=True).first()
                    if not domain:
                        raise ValueError('No primary domain found for tenant')

                    # Generate password reset token instead of temp_password
                    from django.utils.http import urlsafe_base64_encode
                    from django.utils.encoding import force_bytes
                    from django.contrib.auth.tokens import default_token_generator
                    
                    uid = urlsafe_base64_encode(force_bytes(admin.pk))
                    token = default_token_generator.make_token(admin)
                    
                    protocol = getattr(settings, 'PROTOCOL', 'https')
                    reset_url = f"{protocol}://{domain.domain}/reset-password?uid={uid}&token={token}"

                # Only update status after everything inside the schema succeeded
                tenant.status = TenantStatus.ACTIVE
                tenant.save()

                # Email is outside the atomic block — a failed email shouldn't
                # roll back the approval. Log the failure instead.
                from core.email_utils import send_tenant_welcome_email
                try:
                    email_sent = send_tenant_welcome_email(
                        admin_email=admin.email,
                        admin_first_name=admin.first_name,
                        school_name=tenant.name,
                        domain=domain.domain,
                        username=admin.email,
                        reset_url=reset_url,
                        has_mobile_access=tenant.has_mobile_access
                    )
                except Exception:
                    email_sent = False  # log this properly in production

                return Response({
                    'success': True,
                    'message': f"School '{tenant.name}' has been approved and activated",
                    'data': {
                        'school_name':      tenant.name,
                        'status':           tenant.status,
                        'admin_email':      admin.email,
                        'domain':           domain.domain,
                        'email_sent':       email_sent,
                        'plan':             tenant.get_plan_name()
                    }
                })

        except Client.DoesNotExist:
            return Response({'error': 'School not found'}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {'error': f'Approval failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """
        POST /api/admin/tenants/{id}/reject/
        Body: { "reason": "...", "delete_tenant": true }
        """
        error_response = self._check_public_schema()
        if error_response:
            return error_response

        tenant = self.get_object()

        if tenant.status == TenantStatus.ACTIVE:
            return Response(
                {'error': 'Cannot reject an active school. Suspend it first.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        reason        = request.data.get('reason', 'Your registration did not meet our requirements.')
        delete_tenant = request.data.get('delete_tenant', False)

        try:
            with schema_context(tenant.schema_name):
                from django.contrib.auth import get_user_model
                User             = get_user_model()
                admin            = User.objects.filter(is_admin=True).first()
                admin_email      = admin.email      if admin else None
                admin_first_name = admin.first_name if admin else 'there'

            from core.email_utils import send_tenant_rejection_email
            if admin_email:
                send_tenant_rejection_email(
                    admin_email=admin_email,
                    admin_first_name=admin_first_name,
                    school_name=tenant.name,
                    reason=reason
                )

            if delete_tenant:
                schema_name = tenant.schema_name
                tenant_name = tenant.name
                tenant.delete()
                with connection.cursor() as cursor:
                    cursor.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
                return Response({
                    'success': True,
                    'message': f"Registration rejected and tenant '{tenant_name}' deleted",
                    'deleted': True
                })

            # ← Mark as rejected when not deleting
            tenant.status            = TenantStatus.REJECTED
            tenant.rejection_reason  = reason
            tenant.save()

            return Response({
                'success': True,
                'message': f"Registration for '{tenant.name}' has been rejected",
                'deleted': False
            })

        except Exception as e:
            return Response(
                {'error': f'Rejection failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def suspend(self, request, pk=None):
        """POST /api/admin/tenants/{id}/suspend/"""
        error_response = self._check_public_schema()
        if error_response:
            return error_response

        tenant = self.get_object()

        if tenant.status != TenantStatus.ACTIVE:
            return Response(
                {'error': 'Only active schools can be suspended'},
                status=status.HTTP_400_BAD_REQUEST
            )

        reason = request.data.get('reason', 'Account suspended by administrator')

        try:
            TenantService.suspend_tenant(tenant.schema_name, reason=reason)
            tenant.refresh_from_db()   # ← get the status TenantService just wrote

            return Response({
                'success': True,
                'message': f"School '{tenant.name}' has been suspended",
                'status':  tenant.status
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """POST /api/admin/tenants/{id}/activate/"""
        error_response = self._check_public_schema()
        if error_response:
            return error_response

        tenant = self.get_object()

        if tenant.status == TenantStatus.ACTIVE:
            return Response(
                {'error': 'School is already active'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            TenantService.activate_tenant(tenant.schema_name)
            tenant.refresh_from_db()   # ← same fix as suspend

            return Response({
                'success': True,
                'message': f"School '{tenant.name}' has been activated",
                'status':  tenant.status
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='enable-mobile')
    def enable_mobile(self, request, pk=None):
        """POST /api/admin/tenants/{id}/enable-mobile/"""
        error_response = self._check_public_schema()
        if error_response:
            return error_response

        tenant = self.get_object()
        tenant.enable_mobile_access()

        return Response({
            'success':           True,
            'message':           f"Mobile access enabled for '{tenant.name}'",
            'plan':              tenant.get_plan_name(),
            'has_mobile_access': tenant.has_mobile_access
        })

    @action(detail=True, methods=['post'], url_path='disable-mobile')
    def disable_mobile(self, request, pk=None):
        """POST /api/admin/tenants/{id}/disable-mobile/"""
        error_response = self._check_public_schema()
        if error_response:
            return error_response

        tenant = self.get_object()
        tenant.disable_mobile_access()

        return Response({
            'success':           True,
            'message':           f"Mobile access disabled for '{tenant.name}'",
            'plan':              tenant.get_plan_name(),
            'has_mobile_access': tenant.has_mobile_access
        })

    @action(detail=True, methods=['post'], url_path='resend-credentials')
    def resend_credentials(self, request, pk=None):
        """
        POST /api/tenants/admin/{id}/resend-credentials/

        Sends a password reset link to the tenant admin's email.
        Use when the school admin hasn't set up their account yet
        or their original email was lost.  Active tenants only.
        """
        error_response = self._check_public_schema()
        if error_response:
            return error_response

        tenant = self.get_object()

        if tenant.status != TenantStatus.ACTIVE:
            return Response(
                {'error': 'Can only resend credentials for active schools.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with schema_context(tenant.schema_name):
                from django.contrib.auth import get_user_model
                from django.contrib.auth.tokens import default_token_generator
                from django.utils.http import urlsafe_base64_encode
                from django.utils.encoding import force_bytes

                User  = get_user_model()
                admin = User.objects.filter(is_admin=True).first()

                if not admin:
                    return Response(
                        {'error': 'No admin user found in tenant schema.'},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                # Reactivate the account if it was ever deactivated
                if not admin.is_active:
                    admin.is_active = True
                    admin.save()

                uid   = urlsafe_base64_encode(force_bytes(admin.pk))
                token = default_token_generator.make_token(admin)

            domain       = tenant.domains.filter(is_primary=True).first()
            subdomain    = domain.domain.split('.')[0] if domain else tenant.schema_name

            # Build reset URL on the school's own subdomain so the link lands
            # on the correct portal and "Go to Login" works without extra params.
            from urllib.parse import urlparse
            frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
            parsed       = urlparse(frontend_url)
            port         = f':{parsed.port}' if parsed.port else ''
            base_host    = parsed.hostname or 'localhost'
            school_host  = f'{subdomain}.{base_host}{port}'
            reset_url    = f'{parsed.scheme}://{school_host}/reset-password?uid={uid}&token={token}'

            from core.email_utils import send_email
            try:
                email_sent = send_email(
                    subject=f"Set Your Password — {tenant.name}",
                    to_email=admin.email,
                    template_name='tenant_password_reset',
                    context={
                        'admin_name':    admin.first_name or 'Admin',
                        'school_name':   tenant.name,
                        'domain':        domain.domain if domain else '',
                        'reset_url':     reset_url,
                        'expiry_hours':  24,
                        'support_email': getattr(settings, 'SUPPORT_EMAIL', 'support@ssync.online'),
                    },
                )
            except Exception:
                email_sent = False

            return Response({
                'success':    True,
                'message':    (
                    f"Password reset link {'sent' if email_sent else 'failed to send'}"
                    f" to {admin.email}"
                ),
                'email_sent':  email_sent,
                'admin_email': admin.email,
            })

        except Exception as e:
            return Response(
                {'error': f'Failed to send reset link: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PasswordResetConfirmView(APIView):
    """
    POST /api/tenants/password-reset/confirm/

    Public endpoint used by the frontend /reset-password page.
    Validates the uid + token (produced by resend-credentials) and
    sets the user's new password inside the correct tenant schema.

    Body: { uid, token, tenant_schema, new_password }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_decode
        from django.utils.encoding import force_str

        uid          = request.data.get('uid', '')
        token        = request.data.get('token', '')
        tenant_slug  = request.data.get('tenant', '')
        new_password = request.data.get('new_password', '')

        if not all([uid, token, tenant_slug, new_password]):
            return Response(
                {'error': 'uid, token, tenant and new_password are all required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(new_password) < 8:
            return Response(
                {'error': 'Password must be at least 8 characters.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Resolve schema_name from the subdomain (tenant slug)
        domain_obj = Domain.objects.filter(domain__startswith=tenant_slug + '.').first()
        if not domain_obj:
            return Response(
                {'error': 'School not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        tenant_schema = domain_obj.tenant.schema_name

        try:
            with schema_context(tenant_schema):
                from django.contrib.auth import get_user_model
                User = get_user_model()

                try:
                    pk   = force_str(urlsafe_base64_decode(uid))
                    user = User.objects.get(pk=pk)
                except (ValueError, TypeError, OverflowError, User.DoesNotExist):
                    return Response(
                        {'error': 'Invalid or expired reset link.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if not default_token_generator.check_token(user, token):
                    return Response(
                        {'error': 'This reset link has expired or was already used. Ask your administrator to send a new one.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                user.set_password(new_password)
                user.is_active = True
                user.save()

            return Response({'success': True, 'message': 'Password set successfully. You can now log in.'})

        except Exception as e:
            return Response(
                {'error': f'Password reset failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TenantBrandingView(APIView):
    """
    GET /api/tenant/branding/

    Returns public branding info for the current tenant schema.
    Called by the school login page before authentication to load
    the school name, logo and primary colour.
    No authentication required.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            tenant = Client.objects.get(schema_name=connection.schema_name)
            return Response({
                'name':                 tenant.name,
                'logo_url':             tenant.get_logo_url(),
                'primary_color':        tenant.primary_color,
                'onboarding_completed': tenant.onboarding_completed,
            })
        except Client.DoesNotExist:
            # Called from public schema — return safe defaults
            return Response({
                'name':                 'SSync',
                'logo_url':             None,
                'primary_color':        '#047857',
                'onboarding_completed': True,
            })


class SchoolSettingsView(APIView):
    """
    GET  /api/tenants/school/settings/ — Fetch school's own settings.
    PATCH /api/tenants/school/settings/ — Update school's own settings.

    Called from the school subdomain by the school admin.
    Resolves the Client record via connection.schema_name (the tenant schema).
    """
    from rest_framework.permissions import IsAuthenticated
    permission_classes = [IsAuthenticated]

    def _get_client(self):
        return Client.objects.get(schema_name=connection.schema_name)

    def _serialize(self, tenant, request):
        return {
            'name':                 tenant.name,
            'contact_phone':        tenant.contact_phone or '',
            'website':              tenant.website or '',
            'address':              tenant.address or '',
            'logo_url':             tenant.get_logo_url(),
            'primary_color':        tenant.primary_color,
            'onboarding_completed': tenant.onboarding_completed,
        }

    def get(self, request):
        if not request.user.is_admin:
            return Response({'error': 'School admin access required.'}, status=status.HTTP_403_FORBIDDEN)
        tenant = self._get_client()
        return Response(self._serialize(tenant, request))

    def patch(self, request):
        if not request.user.is_admin:
            return Response({'error': 'School admin access required.'}, status=status.HTTP_403_FORBIDDEN)

        tenant = self._get_client()

        # Updatable text fields
        allowed = ('name', 'contact_phone', 'website', 'address', 'primary_color', 'onboarding_completed')
        for field in allowed:
            if field in request.data:
                setattr(tenant, field, request.data[field])

        # Logo file upload (multipart)
        if 'logo' in request.FILES:
            tenant.logo = request.FILES['logo']

        tenant.save()
        return Response(self._serialize(tenant, request))


# tenants/views.py — InspectorViewSet

class InspectorViewSet(viewsets.ModelViewSet):
    """
    Super Admin — full CRUD for inspector accounts.
    """
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        """
        Override queryset to return empty list instead of 404
        when no inspectors exist, and to scope to public schema.
        """
        try:
            return (
                Inspector.objects
                .select_related('user')
                .prefetch_related('assigned_tenants')
                .order_by('-created_at')
            )
        except Exception:
            # Table might not exist yet, return empty queryset safely
            return Inspector.objects.none()

    def get_serializer_class(self):
        if self.action == 'create':
            return InspectorCreateSerializer
        if self.action in ('update', 'partial_update'):
            return InspectorUpdateSerializer
        return InspectorSerializer

    # ── List — always returns array, never 404 ────────────────────────────────

    def list(self, request, *args, **kwargs):
        queryset   = self.get_queryset()
        serializer = InspectorSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    # ── Create ────────────────────────────────────────────────────────────────

    def create(self, request):
        serializer = InspectorCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            inspector, temp_password = serializer.save()
        except Exception as e:
            return Response(
                {'success': False, 'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                'success':       True,
                'message':       f"Inspector account created for {inspector.user.email}",
                'inspector':     InspectorSerializer(inspector).data,
                'temp_password': temp_password,
            },
            status=status.HTTP_201_CREATED,
        )

    # ── Update (PATCH only) ───────────────────────────────────────────────────

    def update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return super().update(request, *args, **kwargs)

    # ── Delete ────────────────────────────────────────────────────────────────

    def destroy(self, request, pk=None):
        inspector = self.get_object()
        email     = inspector.user.email
        inspector.delete()
        return Response(
            {'success': True, 'message': f"Inspector '{email}' removed"},
            status=status.HTTP_200_OK,
        )

    # ── Assign schools ────────────────────────────────────────────────────────

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        inspector  = self.get_object()
        tenant_ids = request.data.get('tenant_ids', [])

        if not isinstance(tenant_ids, list):
            return Response(
                {'error': 'tenant_ids must be a list'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            inspector.assigned_tenants.set(tenant_ids)
        except Exception as e:
            return Response(
                {'error': f'Failed to assign schools: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({
            'success':        True,
            'message':        f"Assigned {len(tenant_ids)} school(s) to {inspector.user.email}",
            'assigned_count': inspector.assigned_tenants.count(),
        })

    # ── Toggle active ─────────────────────────────────────────────────────────

    @action(detail=True, methods=['post'], url_path='toggle-active')
    def toggle_active(self, request, pk=None):
        inspector           = self.get_object()
        new_state           = not inspector.is_active
        inspector.is_active = new_state
        inspector.save(update_fields=['is_active'])

        inspector.user.is_active = new_state
        inspector.user.save(update_fields=['is_active'])

        label = 'activated' if new_state else 'deactivated'
        return Response({
            'success':   True,
            'message':   f"Inspector '{inspector.user.email}' {label}",
            'is_active': new_state,
        })


class SchoolSearchView(APIView):
    """
    GET /api/tenants/search/?q=<query>

    Public endpoint for searching active schools by name.
    Returns matching schools with their subdomain, logo, and name.
    Used by the landing page "Find Your School" modal.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        query = request.query_params.get('q', '').strip()
        if len(query) < 2:
            return Response([])

        # Only search active tenants, exclude the public schema
        tenants = Client.objects.filter(
            status=TenantStatus.ACTIVE,
            name__icontains=query
        ).exclude(
            schema_name='public'
        )[:10]  # Limit to 10 results

        results = []
        for tenant in tenants:
            # Get the primary domain to extract the subdomain
            domain = tenant.domains.filter(is_primary=True).first()
            subdomain = None
            if domain:
                # Domain is stored as 'abchigh.localhost' or 'abchigh.ssync.online'
                # Extract subdomain by removing the base domain suffix
                base_domain = settings.BASE_DOMAIN
                if domain.domain.endswith(f'.{base_domain}'):
                    subdomain = domain.domain[:-(len(base_domain) + 1)]
                else:
                    subdomain = domain.domain.split('.')[0]

            results.append({
                'name': tenant.name,
                'subdomain': subdomain,
                'logo_url': tenant.get_logo_url(),
                'primary_color': tenant.primary_color,
            })

        return Response(results)