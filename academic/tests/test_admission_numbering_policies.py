from school.testcases import TenantTestCase
from django_tenants.utils import schema_context
from rest_framework.test import APIClient

from academic.admission_numbers import AdmissionNumberService, ApplicationNumberService
from academic.models import (
    AdmissionApplicationNumberPolicy, AdmissionNumberSequence,
    NumberResetPolicy, Student, StudentAdmissionNumberPolicy,
)
from academic.tests.admissions_support import make_admissions_structure, make_application
from users.models import CustomUser
from tenants.models import Client as SchoolTenant, Domain, TenantStatus


class AdmissionNumberingPolicyTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.name = "Admissions Numbering Policy School"
        tenant.status = TenantStatus.ACTIVE

    @classmethod
    def setup_domain(cls, domain):
        domain.is_primary = True
        return domain

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with schema_context("public"):
            cls.other_tenant = SchoolTenant(
                schema_name="admissions_numbering_other",
                name="Other Numbering School",
                status=TenantStatus.ACTIVE,
            )
            cls.other_tenant.auto_create_schema = True
            cls.other_tenant.save(verbosity=0)
            cls.other_domain = Domain.objects.create(
                tenant=cls.other_tenant,
                domain="admissions-numbering-other.test.com",
                is_primary=True,
            )

    @classmethod
    def tearDownClass(cls):
        try:
            with schema_context("public"):
                cls.other_domain.delete()
                cls.other_tenant.delete(force_drop=True)
        finally:
            super().tearDownClass()

    def setUp(self):
        self.year, self.grade, self.classroom, self.session = make_admissions_structure()

    def test_defaults_remain_compatible_and_sequences_are_independent(self):
        student = Student.objects.create(first_name="Default", last_name="Student", parent_contact="08070000001")
        application = make_application(self.session, self.grade)
        self.assertRegex(student.admission_number, r"^ADM-\d{4}-\d{4,}$")
        self.assertRegex(application.application_number, r"^ADM/2035/\d{3,}$")

    def test_custom_patterns_year2_no_year_and_policy_changes_preserve_history(self):
        StudentAdmissionNumberPolicy.objects.create(
            pattern="{PREFIX}/ADM/{YEAR2}/{SEQ}", prefix="GVA",
            sequence_width=4, reset_policy=NumberResetPolicy.NEVER,
        )
        first = Student.objects.create(first_name="First", last_name="Student", parent_contact="08070000002")
        self.assertRegex(first.admission_number, r"^GVA/ADM/\d{2}/\d{4,}$")
        policy = StudentAdmissionNumberPolicy.objects.get()
        policy.pattern = "{PREFIX}-{SEQ}"
        policy.prefix = "STU"
        policy.sequence_width = 6
        policy.save()
        second = Student.objects.create(first_name="Second", last_name="Student", parent_contact="08070000003")
        first.refresh_from_db()
        self.assertTrue(second.admission_number.startswith("STU-"))
        self.assertTrue(first.admission_number.startswith("GVA/ADM/"))

    def test_preview_does_not_consume_sequence(self):
        preview = AdmissionNumberService.preview()
        student = Student.objects.create(first_name="Preview", last_name="Student", parent_contact="08070000004")
        self.assertEqual(student.admission_number, preview)

    def test_never_reset_scope_continues_when_year_changes(self):
        StudentAdmissionNumberPolicy.objects.create(
            pattern="{PREFIX}-{SEQ}", prefix="STU", sequence_width=2,
            reset_policy=NumberResetPolicy.NEVER,
        )
        first = AdmissionNumberService.allocate(year=2035)
        second = AdmissionNumberService.allocate(year=2036)
        self.assertEqual((first, second), ("STU-01", "STU-02"))

    def test_padding_is_a_minimum_and_sequence_can_grow(self):
        StudentAdmissionNumberPolicy.objects.create(
            pattern="{PREFIX}-{SEQ}", prefix="STU", sequence_width=2,
            reset_policy=NumberResetPolicy.NEVER,
        )
        AdmissionNumberSequence.objects.create(
            reset_policy=NumberResetPolicy.NEVER,
            scope_key="global", last_value=99,
        )
        self.assertEqual(AdmissionNumberService.allocate(year=2035), "STU-100")

    def test_custom_application_policy_applies_only_to_future_applications(self):
        first = make_application(self.session, self.grade, suffix="before")
        AdmissionApplicationNumberPolicy.objects.create(
            pattern="{PREFIX}/{YEAR2}/{SEQ}", prefix="APP",
            sequence_width=5, reset_policy=NumberResetPolicy.ACADEMIC_YEAR,
        )
        preview = ApplicationNumberService.preview(self.session)
        second = make_application(self.session, self.grade, suffix="after")
        first.refresh_from_db()
        self.assertEqual(second.application_number, preview)
        self.assertTrue(second.application_number.startswith("APP/35/"))
        self.assertTrue(first.application_number.startswith("ADM/2035/"))

    def test_number_policy_api_is_school_admin_only(self):
        admin = CustomUser.objects.create_user(email="admin@number.test", password="x", is_admin=True)
        staff = CustomUser.objects.create_user(email="staff@number.test", password="x", is_staff=True)
        url = "/api/admissions/numbering/student/"
        client = APIClient(HTTP_HOST=self.domain.domain)
        for actor in (None, staff):
            client.force_authenticate(actor)
            self.assertIn(client.get(url).status_code, (401, 403))
        client.force_authenticate(admin)
        response = client.patch(url, {
            "pattern": "{PREFIX}/{YEAR}/{SEQ}", "prefix": "GVA",
            "sequence_width": 4, "reset_policy": "academic_year",
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("preview", response.data)

    def test_student_number_policy_is_tenant_local(self):
        with schema_context(self.other_tenant.schema_name):
            StudentAdmissionNumberPolicy.objects.create(
                pattern="{PREFIX}/{SEQ}", prefix="OTHER", sequence_width=5,
                reset_policy=NumberResetPolicy.NEVER,
            )
        student = Student.objects.create(
            first_name="Local", last_name="Student", parent_contact="08070000009",
        )
        self.assertTrue(student.admission_number.startswith("ADM-"))
        self.assertFalse(StudentAdmissionNumberPolicy.objects.exists())
