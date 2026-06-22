# tenants/tasks.py

from celery import shared_task
from django.utils.timezone import now


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
        .exclude(status__in=[TenantStatus.PENDING, TenantStatus.REJECTED])
        .values_list('pk', flat=True)
    )

    for tenant_id in tenant_ids:
        sync_tenant_stats.delay(tenant_id)