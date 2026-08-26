from django.db import connection
from django.urls import reverse
from django_tenants.utils import schema_context

from academic.models import Student
from tenants.models import Client as SchoolTenant, Domain, TenantStatus
from .tests.support import ReportsTestCase


class ReportScopingTests(ReportsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with schema_context("public"):
            cls.other_tenant = SchoolTenant(
                schema_name="reports_isolation_other", name="Other Reports School",
                status=TenantStatus.ACTIVE,
            )
            cls.other_tenant.auto_create_schema = True
            cls.other_tenant.save(verbosity=0)
            cls.other_domain = Domain.objects.create(
                tenant=cls.other_tenant, domain="reports-isolation-other.test.com",
                is_primary=True,
            )
        with schema_context(cls.other_tenant.schema_name):
            cls.cross_tenant_student_id = Student.objects.create(
                pk=900001, first_name="Other Tenant", last_name="Student",
                parent_contact="08095550999",
            ).pk
        connection.set_tenant(cls.tenant)

    @classmethod
    def tearDownClass(cls):
        try:
            with schema_context("public"):
                cls.other_domain.delete()
                cls.other_tenant.delete(force_drop=True)
        finally:
            super().tearDownClass()

    def test_teacher_academic_scope_is_assigned_students_only(self):
        response = self.get_as(self.teacher_user, reverse("academic-report"))
        numbers = {row["admission_number"] for row in response.data["results"]}
        self.assertEqual(numbers, {self.own_student.admission_number})
        self.assertNotIn("balance", response.data["results"][0])
        self.assertNotIn("total_fees", response.data["results"][0])

    def test_teacher_filters_cannot_broaden_scope(self):
        response = self.get_as(
            self.teacher_user, reverse("academic-report"),
            {"student": self.other_student.pk},
        )
        self.assertEqual(response.data["results"], [])
        response = self.get_as(
            self.teacher_user, reverse("academic-report"),
            {"classroom": self.other_class.pk},
        )
        self.assertEqual(response.data["results"], [])

    def test_teacher_attendance_is_assigned_classroom_only(self):
        response = self.get_as(self.teacher_user, reverse("attendance-report"))
        names = {row["class_name"] for row in response.data["records"]}
        self.assertEqual(names, {self.own_class.name})
        response = self.get_as(
            self.teacher_user, reverse("attendance-report"),
            {"classroom": self.other_class.pk},
        )
        self.assertEqual(response.data["records"], [])

    def test_admin_filter_narrows_tenant_scope(self):
        response = self.get_as(
            self.admin, reverse("student-report"), {"student": self.own_student.pk},
        )
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["admission_number"], self.own_student.admission_number)

    def test_invalid_period_and_term_year_return_400(self):
        response = self.get_as(
            self.admin, reverse("attendance-report"),
            {"date_from": "2032-10-02", "date_to": "2032-10-01"},
        )
        self.assertEqual(response.status_code, 400)

    def test_accountant_cannot_inject_student_into_academic_report(self):
        response = self.get_as(
            self.accountant, reverse("academic-report"),
            {"student": self.own_student.pk},
        )
        self.assertEqual(response.status_code, 403)

    def test_cross_tenant_student_filter_is_invalid_in_current_schema(self):
        response = self.get_as(
            self.admin, reverse("student-report"),
            {"student": self.cross_tenant_student_id},
        )
        self.assertEqual(response.status_code, 400)
