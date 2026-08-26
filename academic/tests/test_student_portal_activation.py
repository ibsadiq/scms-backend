from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework.test import APIClient

from academic.models import Student
from academic.tests.admissions_support import make_admissions_structure
from tenants.models import TenantStatus
from school.testcases import TenantTestCase


class StudentPortalActivationTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.status = TenantStatus.ACTIVE

    def setUp(self):
        _, _, classroom, _ = make_admissions_structure()
        self.client = APIClient(HTTP_HOST=self.domain.domain)
        self.student = Student.objects.create(
            first_name="Portal",
            last_name="Student",
            parent_contact="08055550101",
            phone_number="08055550202",
            classroom=classroom,
            can_login=False,
        )
        self.url = "/api/academic/students/auth/register/"
        self.payload = {
            "admission_number": self.student.admission_number,
            "phone_number": "08055550202",
            "password": "SecurePassword123",
            "password_confirm": "SecurePassword123",
        }

    def test_activation_requires_admin_to_enable_portal_access(self):
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.student.refresh_from_db()
        self.assertIsNone(self.student.user_id)

    def test_enabled_student_can_activate_and_is_linked_to_account(self):
        Student.objects.filter(pk=self.student.pk).update(can_login=True)
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        self.student.refresh_from_db()
        self.assertIsNotNone(self.student.user_id)
        self.assertEqual(self.student.phone_number, self.payload["phone_number"])
        self.assertTrue(self.student.user.is_student)
        self.assertTrue(self.student.user.check_password(self.payload["password"]))
        self.assertTrue(Group.objects.get(name="student").user_set.filter(pk=self.student.user_id).exists())
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_student_cannot_activate_twice(self):
        Student.objects.filter(pk=self.student.pk).update(can_login=True)
        first = self.client.post(self.url, self.payload, format="json")
        second = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)

    def test_activation_phone_must_match_student_record(self):
        Student.objects.filter(pk=self.student.pk).update(can_login=True)
        response = self.client.post(
            self.url,
            {**self.payload, "phone_number": "08000000000"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.student.refresh_from_db()
        self.assertIsNone(self.student.user_id)
