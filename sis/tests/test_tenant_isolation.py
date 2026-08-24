import uuid

from django.contrib.auth import get_user_model
from django.urls import reverse
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework.test import APIClient

from academic.models import Student
from school.testcases import TenantTransactionTestCase
from tenants.models import Client, TenantStatus


User = get_user_model()


class SISStudentTenantIsolationTests(TenantTransactionTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = "SIS Tenant A"
        tenant.status = TenantStatus.ACTIVE

    def setUp(self):
        self.admin_a = User.objects.create_user(email="sis-admin-a@test", password="x", is_admin=True)
        self.student_a = Student.objects.create(
            first_name="Tenant A", last_name="Student", parent_contact="08220000001"
        )

        suffix = uuid.uuid4().hex[:10]
        with schema_context(get_public_schema_name()):
            self.tenant_b = Client(
                schema_name=f"test_sis_b_{suffix}", name="SIS Tenant B", status=TenantStatus.ACTIVE
            )
            self.tenant_b.auto_create_schema = True
            self.tenant_b.save(verbosity=0)

        with schema_context(self.tenant_b.schema_name):
            Student.objects.create(
                first_name="Tenant B", last_name="Filler", parent_contact="08220000002"
            )
            self.student_b = Student.objects.create(
                first_name="Secret Tenant B", last_name="Student", parent_contact="08220000003"
            )

    def client_for_tenant_a(self):
        client = APIClient(HTTP_HOST=self.domain.domain)
        client.force_authenticate(user=self.admin_a)
        return client

    def tearDown(self):
        with schema_context(get_public_schema_name()):
            self.tenant_b.delete(force_drop=True)

    def test_cross_tenant_retrieve_filter_and_search_cannot_resolve_student(self):
        self.assertNotIn("_", self.domain.domain)
        self.assertFalse(Student.objects.filter(pk=self.student_b.pk).exists())
        detail_client = self.client_for_tenant_a()
        self.assertEqual(
            detail_client.get(reverse("student-detail", args=(self.student_b.pk,))).status_code,
            404,
        )

        collection_client = self.client_for_tenant_a()
        list_url = reverse("students-list")
        response = collection_client.get(list_url, {"student": self.student_b.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("results", response.data), [])
        response = collection_client.get(list_url, {"search": "Secret Tenant B"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("results", response.data), [])
