import uuid

from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework.test import APIRequestFactory, force_authenticate

from api.jobs.models import BackgroundJob
from api.jobs.services import BackgroundJobService
from api.jobs.views import BackgroundJobDetailView
from school.testcases import TenantTransactionTestCase
from tenants.models import Client, TenantStatus
from users.models import CustomUser


class BackgroundJobTenantIsolationTests(TenantTransactionTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = "Job Tenant A"
        tenant.status = TenantStatus.ACTIVE

    def setUp(self):
        with schema_context(self.tenant.schema_name):
            self.user_a = CustomUser.objects.create_user(email="job-a@test", password="x")
            self.job_a = BackgroundJob.objects.create(
                created_by=self.user_a, job_type="TENANT_EXECUTION"
            )
            # This is the same explicit-schema boundary used by migrated workers.
            BackgroundJobService.mark_started(self.job_a.public_id)
            BackgroundJobService.mark_success(self.job_a.public_id, {"records": 1})

        suffix = uuid.uuid4().hex[:10]
        with schema_context(get_public_schema_name()):
            self.tenant_b = Client(
                schema_name=f"test_job_b_{suffix}",
                name="Job Tenant B",
                status=TenantStatus.ACTIVE,
            )
            self.tenant_b.auto_create_schema = True
            self.tenant_b.save(verbosity=0)
        with schema_context(self.tenant_b.schema_name):
            self.user_b = CustomUser.objects.create_user(email=f"job-b-{suffix}@test", password="x")

    def tearDown(self):
        with schema_context(get_public_schema_name()):
            self.tenant_b.delete(force_drop=True)

    def test_worker_result_stays_in_tenant_a_and_tenant_b_cannot_resolve_it(self):
        with schema_context(self.tenant_b.schema_name):
            self.assertFalse(BackgroundJob.objects.filter(public_id=self.job_a.public_id).exists())
            request = APIRequestFactory().get(f"/api/jobs/{self.job_a.public_id}/")
            force_authenticate(request, user=self.user_b)
            response = BackgroundJobDetailView.as_view()(
                request, public_id=self.job_a.public_id
            )
            self.assertEqual(response.status_code, 404)

        with schema_context(self.tenant.schema_name):
            self.job_a.refresh_from_db()
            self.assertEqual(self.job_a.status, BackgroundJob.Status.SUCCESS)
            self.assertEqual(self.job_a.safe_result, {"records": 1})
