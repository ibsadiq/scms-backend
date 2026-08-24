from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from school.testcases import TenantTestCase

from academic.models import Department, Staff, Teacher
from tenants.models import Client, Domain, TenantStatus

User = get_user_model()


class StaffEndpointTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.name = "Staff Search Test School"
        tenant.status = TenantStatus.ACTIVE
        return super().setup_tenant(tenant)

    @classmethod
    def setup_domain(cls, domain):
        domain.is_primary = True
        return domain

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from django_tenants.utils import schema_context
        with schema_context("public"):
            cls.other_tenant = Client(
                schema_name="staff_search_other",
                name="Other Staff School",
                status=TenantStatus.ACTIVE,
            )
            cls.other_tenant.auto_create_schema = True
            cls.other_tenant.save(verbosity=0)
            cls.other_domain = Domain.objects.create(
                tenant=cls.other_tenant,
                domain="other-staff-school.test",
                is_primary=True,
            )

    @classmethod
    def tearDownClass(cls):
        try:
            from django_tenants.utils import schema_context
            with schema_context("public"):
                cls.other_domain.delete()
                cls.other_tenant.delete(force_drop=True)
        finally:
            super().tearDownClass()

    def setUp(self):
        self.client = APIClient(HTTP_HOST=self.domain.domain)

        # Department
        self.dept_science = Department.objects.create(name="Science Department")
        self.dept_arts = Department.objects.create(name="Arts Department")

        # School Admin
        self.admin = User.objects.create_user(
            email="schooladmin@stafftest.test",
            password="password123",
            first_name="Admin",
            last_name="User",
            is_admin=True,
        )

        # Staff 1: Teacher
        self.teacher_user = User.objects.create_user(
            email="teacher.one@stafftest.test",
            password="password123",
            first_name="Grace",
            last_name="Okafor",
            is_teacher=True,
        )
        self.teacher_profile = Teacher.objects.create(
            user=self.teacher_user,
            designation="Physics Teacher",
        )
        self.teacher_profile.refresh_from_db()
        self.staff_teacher = self.teacher_profile.staff
        self.staff_teacher.department = self.dept_science
        self.staff_teacher.save(update_fields=["department"])

        # Staff 2: Accountant / Non-teaching Staff
        self.accountant_user = User.objects.create_user(
            email="bursar@stafftest.test",
            password="password123",
            first_name="Emeka",
            last_name="Nwosu",
            is_accountant=True,
        )
        self.staff_accountant = Staff.objects.create(
            user=self.accountant_user,
            role=Staff.Role.ACCOUNTANT,
            designation="Chief Accountant",
            department=self.dept_arts,
            is_active=True,
        )

        # Staff 3: Inactive Staff
        self.staff_inactive = Staff.objects.create(
            role=Staff.Role.OTHER,
            designation="Former Caretaker",
            is_active=False,
        )

        # Other non-admin users
        self.student_user = User.objects.create_user(
            email="student@stafftest.test", password="password123", is_student=True
        )
        self.parent_user = User.objects.create_user(
            email="parent@stafftest.test", password="password123", is_parent=True
        )
        self.ordinary_user = User.objects.create_user(
            email="ordinary@stafftest.test", password="password123"
        )
        self.django_staff_user = User.objects.create_user(
            email="djangostaff@stafftest.test", password="password123", is_staff=True
        )

    def test_school_admin_can_list_staff_with_canonical_pks(self):
        self.client.force_authenticate(self.admin)
        url = reverse("staff-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        results = response.data.get("results", response.data)
        self.assertGreaterEqual(len(results), 3)

        # Verify Staff PK is the Staff model ID, NOT user.id or teacher.id
        staff_teacher_data = next((s for s in results if s["id"] == self.staff_teacher.id), None)
        self.assertIsNotNone(staff_teacher_data)
        self.assertEqual(staff_teacher_data["id"], self.staff_teacher.id)
        self.assertEqual(staff_teacher_data["staff_id"], self.staff_teacher.staff_id)
        self.assertEqual(staff_teacher_data["full_name"], "Grace Okafor")
        self.assertEqual(staff_teacher_data["first_name"], "Grace")
        self.assertEqual(staff_teacher_data["last_name"], "Okafor")
        self.assertEqual(staff_teacher_data["role"], Staff.Role.TEACHER)
        self.assertEqual(staff_teacher_data["designation"], "Physics Teacher")
        self.assertEqual(staff_teacher_data["department_name"], "Science Department")
        self.assertEqual(staff_teacher_data["is_active"], True)

    def test_response_omits_sensitive_internals_and_django_is_staff(self):
        self.client.force_authenticate(self.admin)
        url = reverse("staff-detail", args=[self.staff_teacher.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.data
        self.assertNotIn("password", data)
        self.assertNotIn("is_staff", data)
        self.assertNotIn("token", data)
        self.assertNotIn("auth", data)
        self.assertNotIn("payroll", data)
        self.assertIn("id", data)
        self.assertIn("staff_id", data)
        self.assertIn("full_name", data)
        self.assertIn("role", data)

    def test_authorization_matrix_denies_unprivileged_roles(self):
        url = reverse("staff-list")
        detail_url = reverse("staff-detail", args=[self.staff_teacher.pk])

        # Anonymous
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.client.get(detail_url).status_code, 401)

        # Student, Parent, Teacher (non-admin), Accountant (non-admin), Ordinary, Django is_staff only
        for user in [
            self.student_user,
            self.parent_user,
            self.teacher_user,
            self.accountant_user,
            self.ordinary_user,
            self.django_staff_user,
        ]:
            self.client.force_authenticate(user)
            self.assertEqual(
                self.client.get(url).status_code,
                403,
                f"User {user.email} should be denied access to staff list",
            )
            self.assertEqual(
                self.client.get(detail_url).status_code,
                403,
                f"User {user.email} should be denied access to staff detail",
            )

    def test_search_and_filters(self):
        self.client.force_authenticate(self.admin)
        url = reverse("staff-list")

        # Search by name "Emeka"
        res_name = self.client.get(f"{url}?search=Emeka")
        self.assertEqual(res_name.status_code, 200)
        results = res_name.data.get("results", res_name.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.staff_accountant.id)

        # Search by staff_id
        res_staff_id = self.client.get(f"{url}?staff_id={self.staff_teacher.staff_id}")
        self.assertEqual(res_staff_id.status_code, 200)
        results = res_staff_id.data.get("results", res_staff_id.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.staff_teacher.id)

        # Filter by role ACCOUNTANT
        res_role = self.client.get(f"{url}?role=ACCOUNTANT")
        self.assertEqual(res_role.status_code, 200)
        results = res_role.data.get("results", res_role.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.staff_accountant.id)

        # Filter by is_active=false
        res_inactive = self.client.get(f"{url}?is_active=false")
        self.assertEqual(res_inactive.status_code, 200)
        results = res_inactive.data.get("results", res_inactive.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.staff_inactive.id)

    def test_tenant_isolation_prevents_cross_tenant_leakage(self):
        from django_tenants.utils import schema_context

        with schema_context(self.other_tenant.schema_name):
            other_staff = Staff.objects.create(
                designation="Other School Principal",
                role=Staff.Role.ADMINISTRATOR,
            )

        # In Tenant A's context, verify other_staff cannot be found or accessed
        self.assertFalse(Staff.objects.filter(pk=other_staff.pk).exists())

        self.client.force_authenticate(self.admin)
        url_list = reverse("staff-list")
        res_list = self.client.get(url_list)
        self.assertEqual(res_list.status_code, 200)
        results = res_list.data.get("results", res_list.data)
        ids = [s["id"] for s in results]
        self.assertNotIn(other_staff.id, ids)
        self.assertIn(self.staff_teacher.id, ids)
        self.assertIn(self.staff_accountant.id, ids)

        # Direct detail request for other_staff.pk from Tenant A must return 404
        url_detail = reverse("staff-detail", args=[other_staff.pk])
        res_detail = self.client.get(url_detail)
        self.assertEqual(res_detail.status_code, 404)

        # Search for other_staff.staff_id from Tenant A must return empty
        res_search = self.client.get(f"{url_list}?search={other_staff.staff_id}")
        self.assertEqual(res_search.status_code, 200)
        search_results = res_search.data.get("results", res_search.data)
        self.assertEqual(len(search_results), 0)


