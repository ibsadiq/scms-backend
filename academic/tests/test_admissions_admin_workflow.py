from unittest.mock import patch

from django.urls import reverse
from school.testcases import TenantTestCase
from rest_framework.test import APIClient

from academic.models import AdmissionStatus
from academic.tests.admissions_support import make_admissions_structure, make_application
from users.models import CustomUser
from tenants.models import TenantStatus


class AdmissionsAdminWorkflowTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.name = "Admissions Admin Workflow School"
        tenant.status = TenantStatus.ACTIVE

    @classmethod
    def setup_domain(cls, domain):
        domain.is_primary = True
        return domain

    def setUp(self):
        self.year, self.grade, self.classroom, self.session = make_admissions_structure()
        self.admin = CustomUser.objects.create_user(email="admin@workflow.test", password="x", is_admin=True)
        self.client = APIClient(HTTP_HOST=self.domain.domain)
        self.client.force_authenticate(self.admin)

    def post_action(self, application, action, data=None):
        return self.client.post(
            reverse(f"admin-admission-application-{action}", args=[application.pk]),
            data or {}, format="json",
        )

    def test_supported_review_approval_and_rejection_transitions(self):
        application = make_application(self.session, self.grade, status=AdmissionStatus.SUBMITTED)
        self.assertEqual(self.post_action(application, "start-review").status_code, 200)
        application.refresh_from_db()
        self.assertEqual(application.status, AdmissionStatus.UNDER_REVIEW)
        self.assertEqual(application.reviewed_by, self.admin)
        self.assertEqual(self.post_action(application, "approve").status_code, 200)
        application.refresh_from_db()
        self.assertEqual(application.status, AdmissionStatus.APPROVED)

        rejected = make_application(self.session, self.grade, suffix="reject", status=AdmissionStatus.SUBMITTED)
        response = self.post_action(rejected, "reject", {"rejection_reason": "Not eligible"})
        self.assertEqual(response.status_code, 200)
        rejected.refresh_from_db()
        self.assertEqual(rejected.status, AdmissionStatus.REJECTED)

    def test_invalid_transitions_are_rejected(self):
        draft = make_application(self.session, self.grade, suffix="draft", status=AdmissionStatus.DRAFT)
        self.assertEqual(self.post_action(draft, "start-review").status_code, 400)
        self.assertEqual(self.post_action(draft, "approve").status_code, 400)
        accepted = make_application(self.session, self.grade, suffix="accepted", status=AdmissionStatus.ACCEPTED)
        self.assertEqual(self.post_action(accepted, "reject", {"rejection_reason": "No"}).status_code, 400)

    def test_application_status_cannot_be_changed_through_patch(self):
        application = make_application(self.session, self.grade, status=AdmissionStatus.SUBMITTED)
        response = self.client.patch(
            reverse("admin-admission-application-detail", args=[application.pk]),
            {"status": AdmissionStatus.ENROLLED}, format="json",
        )
        self.assertEqual(response.status_code, 400)
        application.refresh_from_db()
        self.assertEqual(application.status, AdmissionStatus.SUBMITTED)

    @patch("academic.services.admission_enrollment_service.AdmissionEnrollmentService._issue_parent_invitation")
    def test_enroll_action_returns_no_plaintext_credentials(self, _invite):
        application = make_application(
            self.session, self.grade, status=AdmissionStatus.ACCEPTED,
        )
        response = self.post_action(
            application, "enroll", {"classroom": self.classroom.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("student_id", response.data)
        self.assertNotIn("password", response.data)
        self.assertNotIn("temporary_password", response.data)
