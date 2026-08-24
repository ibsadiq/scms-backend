from datetime import date

from academic.models import Student

from .support import SISAccessTestCase


class SISStudentFilterTests(SISAccessTestCase):
    def setUp(self):
        super().setUp()
        self.inactive = Student.objects.create(
            first_name="Inactive", last_name="Learner", parent_contact="08110000003"
        )
        Student.objects.filter(pk=self.inactive.pk).update(is_active=False)
        self.inactive.refresh_from_db()
        self.graduated = Student.objects.create(
            first_name="Graduated", last_name="Learner", parent_contact="08110000004",
            graduation_date=date(2028, 7, 1),
        )
        self.withdrawn = Student.objects.create(
            first_name="Withdrawn", last_name="Learner", parent_contact="08110000005",
            date_dismissed=date(2028, 6, 1),
        )

    def test_stable_status_mappings_and_case_handling(self):
        expected = {
            "ACTIVE": {self.own_student.id, self.other_student.id},
            "inactive": {self.inactive.id},
            "Graduated": {self.graduated.id},
            "withdrawn": {self.withdrawn.id},
        }
        for value, ids in expected.items():
            self.assertEqual(self.list_ids(self.admin, {"status": value})[1], ids)

    def test_invalid_status_returns_400(self):
        response, _ = self.list_ids(self.admin, {"status": "suspended"})
        self.assertEqual(response.status_code, 400)

    def test_teacher_filters_and_search_only_narrow_scope(self):
        response, ids = self.list_ids(self.teacher_user, {"classroom": self.other_class.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ids, set())
        self.assertEqual(self.list_ids(self.teacher_user, {"search": "Other"})[1], set())
        self.assertEqual(
            self.list_ids(self.teacher_user, {"search": self.own_student.admission_number})[1],
            {self.own_student.id},
        )
