from academic.models import Student, StudentsMedicalHistory, StudentsPreviousAcademicHistory

from .support import SISAccessTestCase


class SISStudentAuthorizationTests(SISAccessTestCase):
    def test_only_admin_can_change_student_portal_access(self):
        url = f"/api/sis/students/{self.other_student.id}/portal-access/"
        Student.objects.filter(pk=self.other_student.pk).update(phone_number="08040000001")
        self.authenticate(self.admin)
        response = self.client.patch(url, {"enabled": True}, format="json")
        self.assertEqual(response.status_code, 200)
        self.other_student.refresh_from_db()
        self.assertTrue(self.other_student.can_login)

        self.authenticate(self.teacher_user)
        self.assertEqual(
            self.client.patch(url, {"enabled": False}, format="json").status_code,
            403,
        )

    def test_student_phone_is_required_before_portal_access_is_enabled(self):
        self.authenticate(self.admin)
        response = self.client.patch(
            f"/api/sis/students/{self.other_student.id}/portal-access/",
            {"enabled": True},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_inactive_student_portal_access_cannot_be_enabled(self):
        Student.objects.filter(pk=self.other_student.pk).update(is_active=False)
        self.authenticate(self.admin)
        response = self.client.patch(
            f"/api/sis/students/{self.other_student.id}/portal-access/",
            {"enabled": True},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_admin_teacher_parent_and_student_read_scopes(self):
        self.assertEqual(self.list_ids(self.admin)[1], {self.own_student.id, self.other_student.id})
        self.assertEqual(self.list_ids(self.teacher_user)[1], {self.own_student.id})
        self.assertEqual(self.list_ids(self.parent_user)[1], {self.own_student.id})
        self.assertEqual(self.list_ids(self.student_user)[1], {self.own_student.id})

    def test_teacher_unrelated_retrieve_is_404(self):
        self.authenticate(self.teacher_user)
        response = self.client.get(f"/api/sis/students/{self.other_student.id}/")
        self.assertEqual(response.status_code, 404)

    def test_accountant_gets_minimal_read_access_but_ordinary_staff_and_anonymous_are_denied(self):
        response, ids = self.list_ids(self.accountant)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ids, {self.own_student.id, self.other_student.id})
        row = self.rows(response)[0]
        self.assertNotIn("parent_contact", row)
        self.assertNotIn("region", row)

        self.authenticate(self.accountant)
        self.assertEqual(
            self.client.post("/api/sis/students/", {}, format="json").status_code,
            403,
        )

        self.assertEqual(self.list_ids(self.staff)[0].status_code, 403)
        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get("/api/sis/students/").status_code, (401, 403))

    def test_non_admin_student_payload_is_minimal(self):
        response, _ = self.list_ids(self.teacher_user)
        row = self.rows(response)[0]
        for field in (
            "parent_contact", "parent_guardian_display", "region", "city", "street",
            "reason_left", "gender", "date_of_birth",
        ):
            self.assertNotIn(field, row)

    def test_related_history_uses_same_student_scope(self):
        StudentsMedicalHistory.objects.create(student=self.own_student, history="Needs inhaler")
        StudentsMedicalHistory.objects.create(student=self.other_student, history="Private record")
        StudentsPreviousAcademicHistory.objects.create(
            student=self.own_student, former_school="Old School", last_gpa=3.5
        )
        self.authenticate(self.teacher_user)
        self.assertEqual(
            self.client.get(f"/api/sis/students/{self.own_student.id}/medical-history/").status_code,
            200,
        )
        self.assertEqual(
            self.client.get(f"/api/sis/students/{self.other_student.id}/medical-history/").status_code,
            404,
        )
        self.authenticate(self.parent_user)
        self.assertEqual(
            self.client.get(f"/api/sis/students/{self.own_student.id}/academic-history/").status_code,
            200,
        )
        self.assertEqual(
            self.client.get(f"/api/sis/students/{self.other_student.id}/academic-history/").status_code,
            404,
        )

    def test_related_history_mutation_remains_admin_only(self):
        self.authenticate(self.parent_user)
        response = self.client.post(
            f"/api/sis/students/{self.own_student.id}/medical-history/",
            {"history": "Attempted write"},
        )
        self.assertEqual(response.status_code, 403)

    def test_student_portal_is_self_only_and_has_no_first_student_fallback(self):
        self.authenticate(self.student_user)
        response = self.client.get("/api/sis/students/portal/profile/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], self.own_student.id)

        self.authenticate(self.teacher_user)
        self.assertEqual(
            self.client.get("/api/sis/students/portal/profile/").status_code,
            403,
        )
