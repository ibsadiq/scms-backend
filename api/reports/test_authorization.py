from django.urls import reverse

from examination.views.result import _term_results_for_user
from .tests.support import ReportsTestCase


class ReportAuthorizationTests(ReportsTestCase):
    def test_admin_can_access_every_interactive_report(self):
        for name in ("student-report", "academic-report", "financial-report", "attendance-report"):
            self.assertEqual(self.get_as(self.admin, reverse(name)).status_code, 200)

    def test_accountant_is_finance_only(self):
        self.assertEqual(self.get_as(self.accountant, reverse("financial-report")).status_code, 200)
        self.assertEqual(self.post_as(self.accountant, reverse("export-financial-excel")).status_code, 200)
        for name in ("student-report", "academic-report", "attendance-report"):
            self.assertEqual(self.get_as(self.accountant, reverse(name)).status_code, 403)

    def test_teacher_is_academic_and_attendance_only(self):
        self.assertEqual(self.get_as(self.teacher_user, reverse("academic-report")).status_code, 200)
        self.assertEqual(self.get_as(self.teacher_user, reverse("attendance-report")).status_code, 200)
        self.assertEqual(self.get_as(self.teacher_user, reverse("financial-report")).status_code, 403)
        self.assertEqual(self.get_as(self.teacher_user, reverse("student-report")).status_code, 403)
        self.assertEqual(self.post_as(self.teacher_user, reverse("export-student-excel")).status_code, 403)

    def test_parent_student_staff_and_anonymous_are_denied(self):
        for actor in (self.parent_user, self.student_user, self.staff):
            for name in ("student-report", "academic-report", "financial-report", "attendance-report"):
                self.assertEqual(self.get_as(actor, reverse(name)).status_code, 403)
        self.client.force_authenticate(None)
        for name in ("student-report", "academic-report", "financial-report", "attendance-report"):
            self.assertIn(self.client.get(reverse(name)).status_code, (401, 403))

    def test_interactive_and_export_permissions_match(self):
        for actor in (self.teacher_user, self.parent_user, self.student_user, self.staff):
            self.assertEqual(self.get_as(actor, reverse("student-report")).status_code, 403)
            self.assertEqual(self.post_as(actor, reverse("export-student-excel")).status_code, 403)
        for actor in (self.teacher_user, self.parent_user, self.student_user, self.staff):
            self.assertEqual(self.get_as(actor, reverse("financial-report")).status_code, 403)
            self.assertEqual(self.post_as(actor, reverse("export-financial-excel")).status_code, 403)

    def test_ordinary_django_staff_has_no_tenant_wide_result_scope(self):
        self.assertFalse(_term_results_for_user(self.staff).exists())
