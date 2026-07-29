# tenants/tasks.py

import logging
from urllib.parse import urlparse
from celery import shared_task
from django.utils.timezone import now
from django.conf import settings


logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def sync_tenant_stats(self, tenant_id):
    """
    Sync cached student/teacher counts for a single tenant.
    Called either directly (on save) or fanned out from sync_all_tenant_stats.
    """
    from .models import Client  # local import avoids circular imports

    try:
        tenant = Client.objects.get(pk=tenant_id)
        stats  = tenant.get_usage_stats()
        Client.objects.filter(pk=tenant_id).update(
            cached_student_count=stats['total_students'],
            cached_teacher_count=stats['total_teachers'],
            stats_last_synced=now(),
        )
    except Client.DoesNotExist:
        pass  # tenant was deleted between task creation and execution
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)  # retry after 60s


@shared_task
def sync_all_tenant_stats():
    """
    Periodic task — fans out sync_tenant_stats for every eligible tenant.
    Runs every 30 minutes via Celery Beat.

    Excluded:
    - pending  → no real data yet, school not approved
    - rejected → data is irrelevant / tenant may be deleted
    - public   → not a real school schema

    Included:
    - active    → primary case
    - suspended → counts still meaningful for admin review
    """
    from .models import Client, TenantStatus

    tenant_ids = (
        Client.objects
        .exclude(schema_name='public')
        .exclude(status__in=[TenantStatus.PENDING, TenantStatus.REJECTED, TenantStatus.FAILED, TenantStatus.PROVISIONING])
        .values_list('pk', flat=True)
    )

    for tenant_id in tenant_ids:
        sync_tenant_stats.delay(tenant_id)


@shared_task(bind=True)
def provision_tenant_task(self, tenant_id, admin_user_id):
    """
    Background task to provision a tenant.
    Creates schema, runs migrations, creates admin user, and initializes data.
    """
    from .models import Client, TenantStatus
    from .services import TenantService
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    
    try:
        tenant = Client.objects.get(pk=tenant_id)
        
        # 1. Setup tenant schema (migrations + admin user + initial data)
        # setup_tenant_schema is decorated with @transaction.atomic
        admin_user = TenantService.setup_tenant_schema(
            tenant=tenant,
            admin_email=tenant.pending_admin_email,
            admin_first_name=tenant.pending_admin_first_name,
            admin_last_name=tenant.pending_admin_last_name,
            admin_phone=tenant.pending_admin_phone,
        )
        
        # 2. Generate password reset token
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes
        from django.contrib.auth.tokens import PasswordResetTokenGenerator
        
        uid = urlsafe_base64_encode(force_bytes(admin_user.pk))
        token = PasswordResetTokenGenerator().make_token(admin_user)
        
        # 3. Build reset URL
        domain = tenant.domains.filter(is_primary=True).first()
        if not domain:
            raise ValueError('No primary domain found for tenant')

        _frontend = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        _parsed = urlparse(_frontend)
        _port = f':{_parsed.port}' if _parsed.port else ''
        _subdomain = domain.domain.split('.')[0]

        reset_url = (
            f"{_parsed.scheme}://{_subdomain}.{_parsed.hostname}{_port}"
            f"/reset-password"
            f"?uid={uid}&token={token}"
        )
        
        # 4. Activate tenant
        try:
            approving_user = User.objects.get(pk=admin_user_id)
        except User.DoesNotExist:
            approving_user = None

        tenant.status = TenantStatus.ACTIVE
        tenant.approved_at = now()
        tenant.approved_by = approving_user
        tenant.save()
        
        # 5. Send welcome email
        try:
            TenantService._send_welcome_email(
                email=tenant.pending_admin_email,
                first_name=tenant.pending_admin_first_name,
                school_name=tenant.name,
                domain=domain.domain,
                username=tenant.pending_admin_email,
                reset_url=reset_url,
                has_mobile=tenant.has_mobile_access,
            )
        except Exception:
            logger.exception("Welcome email failed for %s", tenant.schema_name)
            
        return {'status': 'success', 'schema_name': tenant.schema_name}

    except Exception as e:
        logger.exception("Failed to provision tenant %s", tenant_id)
        try:
            tenant = Client.objects.get(pk=tenant_id)
            tenant.status = TenantStatus.FAILED
            tenant.rejection_reason = f"Provisioning failed: {str(e)}"
            tenant.save()
        except Exception:
            pass
        
        return {'status': 'failed', 'error': str(e)}