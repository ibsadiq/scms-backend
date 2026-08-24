from django.urls import NoReverseMatch, reverse
from school.testcases import TenantTestCase
from rest_framework.test import APIClient

from academic.models import AdmissionStatus
from academic.tests.admissions_support import make_admissions_structure, make_application
from academic.views.admission_admin import (
    AdmissionApplicationAdminViewSet, AdmissionAssessmentAdminViewSet,
    AdmissionDocumentAdminViewSet, AdmissionFeeStructureAdminViewSet,
    AdmissionSessionAdminViewSet, AssessmentCriterionAdminViewSet,
    AssessmentTemplateAdminViewSet,
)
from academic.permissions import IsSchoolAdmin
from users.models import CustomUser
from tenants.models import TenantStatus


class AdmissionsAdminAuthorizationTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.name = "Admissions Admin Authorization School"
        tenant.status = TenantStatus.ACTIVE

    @classmethod
    def setup_domain(cls, domain):
        domain.is_primary = True
        return domain

    def setUp(self):
        self.year, self.grade, self.classroom, self.session = make_admissions_structure()
        self.application = make_application(
            self.session, self.grade, status=AdmissionStatus.SUBMITTED,
        )
        self.client = APIClient(HTTP_HOST=self.domain.domain)
        self.admin = CustomUser.objects.create_user(email="admin@admissions.test", password="x", is_admin=True)
        self.users = [
            CustomUser.objects.create_user(email="teacher@admissions.test", password="x", is_teacher=True),
            CustomUser.objects.create_user(email="accountant@admissions.test", password="x", is_accountant=True),
            CustomUser.objects.create_user(email="student@admissions.test", password="x", is_student=True),
            CustomUser.objects.create_user(email="parent@admissions.test", password="x", is_parent=True),
            CustomUser.objects.create_user(email="staff@admissions.test", password="x", is_staff=True),
            CustomUser.objects.create_user(email="ordinary@admissions.test", password="x"),
        ]

    def test_every_admissions_admin_viewset_uses_school_admin_permission(self):
        for view in (
            AdmissionSessionAdminViewSet, AdmissionFeeStructureAdminViewSet,
            AdmissionApplicationAdminViewSet, AdmissionDocumentAdminViewSet,
            AdmissionAssessmentAdminViewSet, AssessmentTemplateAdminViewSet,
            AssessmentCriterionAdminViewSet,
        ):
            self.assertEqual(view.permission_classes, [IsSchoolAdmin])

    def test_role_matrix_denies_non_admin_and_allows_school_admin(self):
        list_url = reverse("admin-admission-application-list")
        action_url = reverse(
            "admin-admission-application-start-review", args=[self.application.pk]
        )
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(list_url).status_code, (401, 403))
        for actor in self.users:
            self.client.force_authenticate(actor)
            self.assertEqual(self.client.get(list_url).status_code, 403)
            self.assertEqual(self.client.post(action_url).status_code, 403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(list_url).status_code, 200)
        self.assertEqual(self.client.post(action_url).status_code, 200)

    def test_stale_exam_and_interview_application_actions_are_unrouted(self):
        for name in (
            "admin-admission-application-schedule-exam",
            "admin-admission-application-mark-exam-completed",
            "admin-admission-application-schedule-interview",
        ):
            with self.assertRaises(NoReverseMatch):
                reverse(name, args=[self.application.pk])
