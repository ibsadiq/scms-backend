import logging

from celery import Task
from django_tenants.utils import schema_context

from .models import BackgroundJob
from .services import BackgroundJobService


logger = logging.getLogger(__name__)


class TenantBackgroundJobTask(Task):
    """Failure boundary for tasks dispatched through BackgroundJobService."""

    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        schema_name = kwargs.get("schema_name")
        job_public_id = kwargs.get("job_public_id")
        if schema_name and job_public_id:
            logger.error(
                "Tenant background job execution failed",
                extra={"job_id": job_public_id},
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            with schema_context(schema_name):
                if not BackgroundJob.objects.filter(
                    public_id=job_public_id, status=BackgroundJob.Status.FAILURE
                ).exists():
                    BackgroundJobService.mark_failure(job_public_id, "JOB_EXECUTION_FAILED")
        super().on_failure(exc, task_id, args, kwargs, einfo)
