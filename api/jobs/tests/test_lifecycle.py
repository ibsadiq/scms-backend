from unittest.mock import Mock

from django.db import transaction
from django_tenants.utils import schema_context

from api.jobs.models import BackgroundJob
from api.jobs.services import BackgroundJobService
from notifications.models import Notification
from notifications.services import NotificationService
from users.models import CustomUser
from .support import JobsTenantTestCase


class BackgroundJobLifecycleTests(JobsTenantTestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(email="lifecycle@jobs.test", password="x")

    def test_record_exists_before_dispatch_and_dispatch_is_after_commit(self):
        task = Mock()
        task.apply_async.return_value = Mock(id="internal-task-id")
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            with transaction.atomic():
                job = BackgroundJobService.create_and_dispatch(
                    task=task, job_type="TEST_JOB", created_by=self.user, task_kwargs={"value": 1}
                )
                self.assertTrue(BackgroundJob.objects.filter(pk=job.pk).exists())
                task.apply_async.assert_not_called()
        self.assertEqual(len(callbacks), 1)
        callbacks[0]()
        task.apply_async.assert_called_once()
        kwargs = task.apply_async.call_args.kwargs["kwargs"]
        self.assertEqual(kwargs["schema_name"], self.tenant.schema_name)
        self.assertEqual(kwargs["job_public_id"], str(job.public_id))
        job.refresh_from_db()
        self.assertEqual(job.celery_task_id, "internal-task-id")

    def test_rollback_does_not_dispatch(self):
        task = Mock()
        try:
            with transaction.atomic():
                BackgroundJobService.create_and_dispatch(
                    task=task, job_type="ROLLBACK", created_by=self.user
                )
                raise RuntimeError("rollback")
        except RuntimeError:
            pass
        task.apply_async.assert_not_called()
        self.assertFalse(BackgroundJob.objects.filter(job_type="ROLLBACK").exists())

    def test_retry_updates_same_job_and_sanitizes_failure(self):
        job = BackgroundJob.objects.create(created_by=self.user, job_type="RETRYABLE")
        BackgroundJobService.mark_started(job.public_id)
        BackgroundJobService.mark_failure(job.public_id, "SAFE_FAILURE")
        BackgroundJobService.mark_started(job.public_id)
        BackgroundJobService.mark_success(job.public_id, {"generated": 1})
        self.assertEqual(BackgroundJob.objects.filter(public_id=job.public_id).count(), 1)
        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.SUCCESS)
        self.assertEqual(job.safe_result, {"generated": 1})
        self.assertEqual(job.error_code, "")

    def test_lifecycle_updates_only_in_explicit_tenant_schema(self):
        job = BackgroundJob.objects.create(created_by=self.user, job_type="TENANT_EXECUTION")
        with schema_context(self.tenant.schema_name):
            BackgroundJobService.mark_started(job.public_id)
            BackgroundJobService.mark_success(job.public_id, {"tenant": "owned"})
        job.refresh_from_db()
        self.assertEqual(job.safe_result, {"tenant": "owned"})

    def test_retry_idempotency_key_does_not_duplicate_notification_side_effect(self):
        job = BackgroundJob.objects.create(created_by=self.user, job_type="FEE_REMINDER")
        key = f"custom-fee-reminder:{job.public_id}:42"
        service = NotificationService()
        for _attempt in range(2):
            service.create_notification(
                recipient=self.user,
                notification_type="fee",
                title="Fee reminder",
                message="A safe reminder",
                send_email=False,
                send_sms=False,
                idempotency_key=key,
            )
        self.assertEqual(Notification.objects.filter(idempotency_key=key).count(), 1)
