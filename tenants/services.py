"""
Tenant Management Service
Handles school registration, tenant creation, and initial setup.
"""
import re
import logging
from urllib.parse import urlparse

from django.db import transaction
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django_tenants.utils import schema_context
from django.conf import settings

from .models import Client, Domain, TenantStatus

logger = logging.getLogger(__name__)

User = get_user_model()


class TenantCreationError(Exception):
    """Custom exception for tenant creation failures"""
    pass


class TenantService:
    """Service for managing tenant lifecycle"""

    # ─── Schema / domain validation ───────────────────────────────────────────

    @staticmethod
    def validate_schema_name(school_name):
        """
        Generate and validate schema name from school name.
        Schema names must be lowercase alphanumeric + underscores.
        """
        schema = re.sub(r'[^a-z0-9_]', '', school_name.lower().replace(' ', '_'))

        if schema and schema[0].isdigit():
            schema = 'school_' + schema

        if not schema:
            schema = 'school'

        schema = schema[:63]

        if Client.objects.filter(schema_name=schema).exists():
            counter = 1
            while Client.objects.filter(schema_name=f"{schema}_{counter}").exists():
                counter += 1
            schema = f"{schema}_{counter}"

        return schema

    @staticmethod
    def validate_domain(domain):
        """Validate domain format and availability."""
        if not re.match(r'^[a-z0-9.-]+$', domain):
            raise TenantCreationError(
                "Domain must contain only lowercase letters, numbers, dots, and hyphens"
            )
        if Domain.objects.filter(domain=domain).exists():
            raise TenantCreationError(f"Domain '{domain}' is already taken")
        return True

    # ─── Tenant creation ──────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def create_tenant(
        school_name,
        subdomain,
        admin_email,
        admin_first_name,
        admin_last_name,
        admin_phone=None,
        contact_email=None,
        contact_phone=None,
        enable_mobile=False,
        auto_activate=False,
    ):
        """
        Create a new tenant with all required setup.

        Args:
            admin_email:    Email used to create the admin account (login credential).
            contact_email:  School's public contact email (optional; falls back to admin_email).
            contact_phone:  School's public contact phone (optional).
            auto_activate:  If False (default), tenant is created as PENDING.

        Returns:
            dict with tenant, domain, admin_user, etc.
        """
        if not school_name or not subdomain or not admin_email:
            raise TenantCreationError("School name, subdomain, and admin email are required")

        full_domain = f"{subdomain}.{settings.BASE_DOMAIN}"
        TenantService.validate_domain(full_domain)
        schema_name = TenantService.validate_schema_name(school_name)

        # 1. Create the tenant record
        tenant = Client.objects.create(
            schema_name=schema_name,
            name=school_name,
            has_mobile_access=enable_mobile,
            contact_email=contact_email or admin_email,
            contact_phone=contact_phone or '',
            # Use proper status field — never touch is_active directly
            status=TenantStatus.ACTIVE if auto_activate else TenantStatus.PENDING,
        )

        # 2. Create the primary domain
        domain = Domain.objects.create(
            domain=full_domain,
            tenant=tenant,
            is_primary=True,
        )

        # 3. Create school admin user inside the tenant schema
        with schema_context(schema_name):
            admin_user = User.objects.create_user(
                email=admin_email,
                password=User.objects.make_random_password(length=20),  # unusable until reset
                first_name=admin_first_name,
                last_name=admin_last_name,
                is_admin=True,
                is_active=True,
            )
            TenantService._initialize_school_data(schema_name)

        # Build password-set URL using FRONTEND_URL (respects dev port)
        _frontend = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        _parsed   = urlparse(_frontend)
        _port     = f':{_parsed.port}' if _parsed.port else ''
        _subdomain = subdomain  # already validated above
        _reset_url = (
            f"{_parsed.scheme}://{_subdomain}.{_parsed.hostname}{_port}"
            f"/reset-password"
            f"?uid={urlsafe_base64_encode(force_bytes(admin_user.pk))}"
            f"&token={PasswordResetTokenGenerator().make_token(admin_user)}"
        )

        # Note: Email notifications were previously sent from inside this
        # service. Move sending of acknowledgement and notification emails to
        # the calling view so that emails are only sent after the view has
        # confirmed the tenant creation completed successfully.

        logger.info("Tenant '%s' created (status=%s)", schema_name, tenant.status)

        return {
            'tenant':           tenant,
            'domain':           domain,
            'admin_user':       admin_user,
            'reset_url':        _reset_url,
            'login_url':        _reset_url,
            'has_mobile_access': enable_mobile,
            'status':           tenant.status,
        }

    # ─── School data initialisation ───────────────────────────────────────────

    @staticmethod
    def _initialize_school_data(schema_name):
        """Initialize default academic year, terms, and grade levels for a new school."""
        from datetime import date
        from administration.models import AcademicYear, Term
        from academic.models import GradeLevel

        with schema_context(schema_name):
            GradeLevel.initialize_defaults()
            current_year  = date.today().year
            academic_year = AcademicYear.objects.create(
                name=f"{current_year}/{current_year + 1}",
                start_date=date(current_year,     9,  1),
                end_date=date(current_year + 1,   6, 30),
                active_year=True,
            )
            Term.objects.bulk_create([
                Term(
                    name="First Term",
                    academic_year=academic_year,
                    start_date=date(current_year,      9,  1),
                    end_date=date(current_year,        12, 15),
                ),
                Term(
                    name="Second Term",
                    academic_year=academic_year,
                    start_date=date(current_year + 1,  1,  5),
                    end_date=date(current_year + 1,    4, 15),
                ),
                Term(
                    name="Third Term",
                    academic_year=academic_year,
                    start_date=date(current_year + 1,  4, 20),
                    end_date=date(current_year + 1,    6, 30),
                ),
            ])

    # ─── Lifecycle actions ────────────────────────────────────────────────────

    @staticmethod
    def activate_tenant(schema_name):
        """
        Activate a suspended tenant.
        Called by the /activate/ ViewSet action.
        """
        try:
            tenant = Client.objects.get(schema_name=schema_name)

            if tenant.status == TenantStatus.ACTIVE:
                raise TenantCreationError(f"Tenant '{schema_name}' is already active")

            tenant.status            = TenantStatus.ACTIVE
            tenant.suspension_reason = None   # clear previous suspension reason
            tenant.save()

            logger.info("Tenant '%s' activated", schema_name)
            return True

        except Client.DoesNotExist:
            raise TenantCreationError(f"Tenant '{schema_name}' not found")

    @staticmethod
    def suspend_tenant(schema_name, reason=None):
        """
        Suspend an active tenant and optionally notify the school admin.
        Called by the /suspend/ ViewSet action.
        """
        try:
            tenant = Client.objects.get(schema_name=schema_name)

            if tenant.status == TenantStatus.SUSPENDED:
                raise TenantCreationError(f"Tenant '{schema_name}' is already suspended")

            tenant.status            = TenantStatus.SUSPENDED
            tenant.suspension_reason = reason
            tenant.save()

            if reason:
                TenantService._send_suspension_email(tenant, reason)

            logger.info("Tenant '%s' suspended. Reason: %s", schema_name, reason)
            return True

        except Client.DoesNotExist:
            raise TenantCreationError(f"Tenant '{schema_name}' not found")

    # ─── Stats (used by the Celery sync task) ─────────────────────────────────

    @staticmethod
    def get_tenant_stats(schema_name):
        """
        Fetch live stats from the tenant's schema.
        Used by tasks.sync_tenant_stats — NOT called on every API request.
        Results are written back to cached_student_count / cached_teacher_count.
        """
        try:
            with schema_context(schema_name):
                from academic.models import Student, Teacher
                from finance.models import Receipt
                from django.db.models import Sum

                return {
                    'total_students': Student.objects.filter(status='Active').count(),
                    'total_teachers': Teacher.objects.count(),
                    'total_revenue':  Receipt.objects.aggregate(
                        total=Sum('amount')
                    )['total'] or 0,
                }
        except Exception as e:
            logger.warning("Could not get live stats for '%s': %s", schema_name, e)
            return {'total_students': 0, 'total_teachers': 0, 'total_revenue': 0}

    # ─── Utility ──────────────────────────────────────────────────────────────

    @staticmethod
    def list_all_tenants():
        """Return all non-public tenants ordered by creation date."""
        return Client.objects.exclude(schema_name='public').order_by('-created_on')

    # ─── Emails ───────────────────────────────────────────────────────────────

    @staticmethod
    def _send_welcome_email(email, first_name, school_name, domain, username, reset_url, has_mobile):
        try:
            from core.email_utils import send_tenant_welcome_email
            send_tenant_welcome_email(
                admin_email=email,
                admin_first_name=first_name,
                school_name=school_name,
                domain=domain,
                username=username,
                reset_url=reset_url,
                has_mobile_access=has_mobile,
            )
            logger.info("Welcome email sent to %s", email)
        except Exception as e:
            logger.warning("Could not send welcome email to %s: %s", email, e)

    @staticmethod
    def _send_pending_approval_email(email, first_name, school_name, domain):
        try:
            from core.email_utils import send_email

            send_email(
                subject=f"Registration Received - {school_name}",
                to_email=email,
                template_name='tenant_pending_approval',
                context={
                    'admin_name':              first_name,
                    'school_name':             school_name,
                    'domain':                  domain,
                    'support_email':           getattr(settings, 'SUPPORT_EMAIL', 'support@ssyncportal.com'),
                    'app_name':                getattr(settings, 'APP_NAME', 'SSync'),
                    'estimated_approval_time': '24 hours',
                },
                fail_silently=False,
            )
            logger.info("Pending approval email sent to %s", email)
        except Exception as e:
            logger.warning("Could not send pending approval email to %s: %s", email, e)

    @staticmethod
    def _notify_super_admin_new_registration(tenant, admin_email, admin_phone=None, admin_name=None):
        try:
            from core.email_utils import send_email

            superusers = User.objects.filter(is_superuser=True, is_active=True)
            if not superusers.exists():
                logger.warning("No superusers found to notify of new registration")
                return

            domain     = tenant.domains.filter(is_primary=True).first()
            # Link to Nuxt frontend admin panel, not Django admin
            review_url = (
                f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')}"
                f"/admin/tenants?highlight={tenant.id}"
            )

            context = {
                'school_name':      tenant.name,
                'schema_name':      tenant.schema_name,
                'domain':           domain.domain if domain else 'N/A',
                'admin_name':       admin_name or admin_email,
                'admin_email':      admin_email,
                'admin_phone':      admin_phone or 'Not provided',
                'plan':             tenant.get_plan_name(),
                'has_mobile_access': tenant.has_mobile_access,
                'review_url':       review_url,
                'app_name':         getattr(settings, 'APP_NAME', 'SSync'),
            }

            for superuser in superusers:
                send_email(
                    subject=f"New School Registration - {tenant.name}",
                    to_email=superuser.email,
                    template_name='admin_new_registration',
                    context={**context, 'school_logo_url': getattr(settings, 'PLATFORM_LOGO_URL', None)},
                    fail_silently=True,
                )

            logger.info("Notified %d super admin(s) of new registration: %s",
                        superusers.count(), tenant.name)

        except Exception as e:
            logger.warning("Could not notify super admins: %s", e)

    @staticmethod
    def _send_suspension_email(tenant, reason):
        try:
            from core.email_utils import send_email

            with schema_context(tenant.schema_name):
                admin = User.objects.filter(is_admin=True).first()
                if not admin:
                    return

                send_email(
                    subject=f"Account Suspended - {tenant.name}",
                    to_email=admin.email,
                    template_name='tenant_suspended',
                    context={
                        'admin_name':    admin.first_name,
                        'school_name':   tenant.name,
                        'reason':        reason,
                        'support_email': getattr(settings, 'SUPPORT_EMAIL', 'support@ssync.online'),
                        'app_name':      getattr(settings, 'APP_NAME', 'SSync'),
                    },
                    fail_silently=True,
                )
                logger.info("Suspension email sent to %s", admin.email)

        except Exception as e:
            logger.warning("Could not send suspension email for '%s': %s", tenant.schema_name, e)