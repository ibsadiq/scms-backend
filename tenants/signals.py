from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Client


@receiver(post_save, sender=Client)
def trigger_stats_sync(sender, instance, created, **kwargs):
    from .tasks import sync_tenant_stats
    from .models import TenantStatus

    if (
        instance.schema_name != 'public'
        and instance.status == TenantStatus.ACTIVE  # not suspended, not pending
    ):
        sync_tenant_stats.delay(instance.pk)