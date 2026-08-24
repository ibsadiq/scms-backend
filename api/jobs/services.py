import logging

from django.db import connection, transaction
from django.utils import timezone
from django_tenants.utils import schema_context

from .models import BackgroundJob


logger = logging.getLogger(__name__)


class BackgroundJobService:
    """Ownership and lifecycle boundary for user-visible Celery work."""

    @classmethod
    def create_and_dispatch(cls, *, task, job_type, created_by, task_kwargs=None):
        schema_name = connection.schema_name
        if not schema_name or schema_name == "public":
            raise ValueError("Tenant background jobs require a tenant schema.")

        job = BackgroundJob.objects.create(created_by=created_by, job_type=job_type)
        kwargs = dict(task_kwargs or {})
        kwargs.update(schema_name=schema_name, job_public_id=str(job.public_id))

        def dispatch():
            try:
                result = task.apply_async(kwargs=kwargs)
                with schema_context(schema_name):
                    BackgroundJob.objects.filter(pk=job.pk).update(celery_task_id=result.id)
            except Exception:
                logger.exception("Background job dispatch failed", extra={"job_id": str(job.public_id)})
                with schema_context(schema_name):
                    BackgroundJob.objects.filter(pk=job.pk).update(
                        status=BackgroundJob.Status.FAILURE,
                        error_code="JOB_DISPATCH_FAILED",
                        completed_at=timezone.now(),
                    )

        transaction.on_commit(dispatch)
        return job

    @staticmethod
    def mark_started(public_id):
        BackgroundJob.objects.filter(public_id=public_id).update(
            status=BackgroundJob.Status.STARTED,
            started_at=timezone.now(),
            error_code="",
        )

    @staticmethod
    def mark_progress(public_id, progress):
        bounded = max(0, min(100, int(progress)))
        BackgroundJob.objects.filter(public_id=public_id).update(progress=bounded)

    @staticmethod
    def mark_success(public_id, safe_result=None):
        BackgroundJob.objects.filter(public_id=public_id).update(
            status=BackgroundJob.Status.SUCCESS,
            progress=100,
            safe_result=safe_result or {},
            error_code="",
            completed_at=timezone.now(),
        )

    @staticmethod
    def mark_failure(public_id, error_code):
        BackgroundJob.objects.filter(public_id=public_id).update(
            status=BackgroundJob.Status.FAILURE,
            safe_result={},
            error_code=error_code,
            completed_at=timezone.now(),
        )
