from django.urls import reverse

from .tests.support import ReportsTestCase


class ReportExportTests(ReportsTestCase):
    def test_admin_student_export_is_identity_only(self):
        response = self.post_as(self.admin, reverse("export-student-excel"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Admission Number", content)
        self.assertNotIn("Balance", content)
        self.assertNotIn("Average Grade", content)
        self.assertNotIn("Medical", content)

    def test_accountant_finance_contract_contains_no_academic_data(self):
        response = self.get_as(self.accountant, reverse("financial-report"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("defaulters", response.data)
        if response.data["defaulters"]:
            row = response.data["defaulters"][0]
            self.assertNotIn("average_grade", row)
            self.assertNotIn("attendance_rate", row)
            self.assertNotIn("student_id", row)

    def test_finance_export_uses_same_filtered_scope(self):
        filters = {"student": self.own_student.pk}
        interactive = self.get_as(self.accountant, reverse("financial-report"), filters)
        exported = self.post_as(self.accountant, reverse("export-financial-excel"), filters)
        self.assertEqual(interactive.status_code, 200)
        self.assertEqual(exported.status_code, 200)
        content = exported.content.decode()
        for item in interactive.data["defaulters"]:
            self.assertIn(item["admission_number"], content)
        self.assertNotIn(self.other_student.admission_number, content)
