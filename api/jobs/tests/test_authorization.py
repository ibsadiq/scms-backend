from types import SimpleNamespace
from unittest.mock import patch

from django.urls import resolve, reverse
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from api.celery_views import CeleryHealthView
from api.jobs.models import BackgroundJob
from users.models import CustomUser
from .support import JobsTenantTestCase


class BackgroundJobAuthorizationTests(JobsTenantTestCase):
    def setUp(self):
        self.client = APIClient(HTTP_HOST=self.domain.domain)
        self.creator = CustomUser.objects.create_user(email="creator@jobs.test", password="x")
        self.other = CustomUser.objects.create_user(email="other@jobs.test", password="x")
        self.staff = CustomUser.objects.create_user(
            email="staff@jobs.test", password="x", is_staff=True
        )
        self.admin = CustomUser.objects.create_user(
            email="admin@jobs.test", password="x", is_admin=True
        )
        self.job = BackgroundJob.objects.create(
            created_by=self.creator,
            job_type="TEST_JOB",
            celery_task_id="raw-secret-task-id",
            safe_result={"count": 2},
        )
        self.url = reverse("background_jobs:detail", args=(self.job.public_id,))

    def get_as(self, user):
        self.client.force_authenticate(user)
        return self.client.get(self.url)

    def test_anonymous_is_denied(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_creator_and_school_admin_can_view_safe_contract(self):
        for user in (self.creator, self.admin):
            response = self.get_as(user)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["id"], str(self.job.public_id))
            self.assertNotIn("celery_task_id", response.data)
            self.assertNotIn("created_by", response.data)

    def test_unrelated_user_and_ordinary_is_staff_are_denied(self):
        for user in (self.other, self.staff):
            self.assertEqual(self.get_as(user).status_code, 403)

    def test_raw_task_status_route_is_removed(self):
        response = self.client.get("/api/tasks/arbitrary-celery-id/")
        self.assertEqual(response.status_code, 404)
        with self.assertRaises(Exception):
            resolve("/api/tasks/arbitrary-celery-id/")

    def test_failure_contract_does_not_leak_internal_details(self):
        self.job.status = BackgroundJob.Status.FAILURE
        self.job.error_code = "REPORT_GENERATION_FAILED"
        self.job.safe_result = {}
        self.job.save()
        body = str(self.get_as(self.creator).data).lower()
        for forbidden in ("traceback", "exception", "select ", self.tenant.schema_name, "/tmp/", "secret"):
            self.assertNotIn(forbidden, body)


class CeleryHealthAuthorizationTests(JobsTenantTestCase):
    def request_for(self, user, tenant):
        request = APIRequestFactory().get("/api/celery/health/")
        request.tenant = tenant
        force_authenticate(request, user=user)
        return CeleryHealthView.as_view()(request)

    def test_tenant_roles_cannot_inspect_worker_topology(self):
        users = (
            CustomUser.objects.create_user(email="admin-health@test", password="x", is_admin=True),
            CustomUser.objects.create_user(email="staff-health@test", password="x", is_staff=True),
            CustomUser.objects.create_user(email="teacher-health@test", password="x", is_teacher=True),
            CustomUser.objects.create_user(email="accountant-health@test", password="x", is_accountant=True),
            CustomUser.objects.create_user(email="student-health@test", password="x", is_student=True),
            CustomUser.objects.create_user(email="parent-health@test", password="x", is_parent=True),
        )
        for user in users:
            response = self.request_for(user, self.tenant)
            self.assertEqual(response.status_code, 403)
            body = str(response.data).lower()
            self.assertNotIn("registered_tasks", body)
            self.assertNotIn("workers", body)

    def test_anonymous_cannot_inspect_worker_topology(self):
        request = APIRequestFactory().get("/api/celery/health/")
        request.tenant = self.tenant
        response = CeleryHealthView.as_view()(request)
        self.assertIn(response.status_code, (401, 403))
        self.assertNotIn("workers", str(response.data).lower())

    def test_superuser_is_not_operator_from_tenant_schema(self):
        user = CustomUser.objects.create_superuser(email="super-health@test", password="x")
        self.assertEqual(self.request_for(user, self.tenant).status_code, 403)

    @patch("api.celery_views.celery_app.control.inspect")
    def test_public_schema_superuser_is_platform_operator(self, inspect):
        inspect.return_value.active.return_value = {"worker-internal": []}
        inspect.return_value.registered.return_value = {"worker-internal": ["task"]}
        inspect.return_value.stats.return_value = {"worker-internal": {}}
        user = CustomUser.objects.create_superuser(email="operator-health@test", password="x")
        public_tenant = SimpleNamespace(schema_name="public")
        response = self.request_for(user, public_tenant)
        self.assertEqual(response.status_code, 200)
