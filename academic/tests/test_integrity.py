from datetime import date

from django.core.exceptions import ValidationError
from school.testcases import TenantTestCase

from academic.models import ClassRoom, GradeLevel, Student
from academic.services.enrollment_service import EnrollmentService
from administration.models import AcademicYear


class AcademicIntegrityTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        return super().setup_tenant(tenant)

    def setUp(self):
        self.year = AcademicYear.objects.create(
            name="2028/2029", start_date=date(2028, 9, 1),
            end_date=date(2029, 7, 1), active_year=True,
        )
        self.grade = GradeLevel.objects.create(
            system_code="JSS_2", section="JSS", default_name="JSS 2", sequence_order=2
        )
        self.room_a = ClassRoom.objects.create(name="A", grade_level=self.grade)
        self.room_b = ClassRoom.objects.create(name="B", grade_level=self.grade)

    def make_student(self, suffix):
        return Student.objects.create(
            first_name="Integrity", last_name=str(suffix),
            parent_contact=f"0808111{suffix:04d}",
        )

    def test_admission_numbers_preserve_format_and_do_not_reuse_deleted_number(self):
        first = self.make_student(1)
        first_number = first.admission_number
        first.delete()
        second = self.make_student(2)
        self.assertRegex(first_number, r"^ADM-\d{4}-\d{4,}$")
        self.assertNotEqual(second.admission_number, first_number)
        self.assertGreater(int(second.admission_number.rsplit("-", 1)[1]), int(first_number.rsplit("-", 1)[1]))

    def test_first_generated_admission_number_preserves_visible_format(self):
        student = self.make_student(6)
        self.assertRegex(student.admission_number, r"^ADM-\d{4}-0001$")

    def test_enrollment_and_movement_synchronize_student_snapshots(self):
        student = self.make_student(3)
        enrollment, created = EnrollmentService.enroll(
            student=student, classroom=self.room_a, academic_year=self.year
        )
        student.refresh_from_db()
        self.room_a.refresh_from_db()
        self.assertTrue(created)
        self.assertEqual(student.classroom, self.room_a)
        self.assertEqual(student.grade_level, self.grade)
        self.assertEqual(self.room_a.occupied_sits, 1)

        moved, created = EnrollmentService.enroll(
            student=student, classroom=self.room_b, academic_year=self.year
        )
        student.refresh_from_db()
        self.room_a.refresh_from_db()
        self.room_b.refresh_from_db()
        self.assertFalse(created)
        self.assertEqual(moved.pk, enrollment.pk)
        self.assertEqual(student.classroom, self.room_b)
        self.assertEqual(student.grade_level, self.grade)
        self.assertEqual(self.room_a.occupied_sits, 0)
        self.assertEqual(self.room_b.occupied_sits, 1)

        EnrollmentService.deactivate(moved)
        student.refresh_from_db()
        self.room_b.refresh_from_db()
        self.assertIsNone(student.classroom)
        self.assertIsNone(student.grade_level)
        self.assertEqual(self.room_b.occupied_sits, 0)

    def test_enrollment_cannot_exceed_locked_classroom_capacity(self):
        self.room_a.capacity = 1
        self.room_a.save(update_fields=("capacity",))
        EnrollmentService.enroll(
            student=self.make_student(8), classroom=self.room_a,
            academic_year=self.year,
        )
        with self.assertRaises(ValidationError):
            EnrollmentService.enroll(
                student=self.make_student(9), classroom=self.room_a,
                academic_year=self.year,
            )
        self.room_a.refresh_from_db()
        self.assertEqual(self.room_a.occupied_sits, 1)

    def test_bulk_enrollment_explicitly_synchronizes_snapshots(self):
        students = [self.make_student(4), self.make_student(5)]
        EnrollmentService.bulk_enroll([
            {"student": student, "classroom": self.room_a, "academic_year": self.year}
            for student in students
        ])
        self.assertEqual(
            set(Student.objects.filter(pk__in=[s.pk for s in students]).values_list("classroom_id", flat=True)),
            {self.room_a.pk},
        )

    def test_failed_movement_rolls_back_enrollment_and_snapshot(self):
        student = self.make_student(7)
        enrollment, _ = EnrollmentService.enroll(
            student=student, classroom=self.room_a, academic_year=self.year
        )
        self.room_b.occupied_sits = self.room_b.capacity
        self.room_b.save(update_fields=("occupied_sits",))
        with self.assertRaises(ValidationError):
            EnrollmentService.enroll(
                student=student, classroom=self.room_b, academic_year=self.year
            )
        enrollment.refresh_from_db()
        student.refresh_from_db()
        self.room_a.refresh_from_db()
        self.room_b.refresh_from_db()
        self.assertEqual(enrollment.classroom_id, self.room_a.pk)
        self.assertEqual(self.room_a.occupied_sits, 1)
        self.assertEqual(self.room_b.occupied_sits, self.room_b.capacity)

    def test_grade_level_defaults_include_nursery_3_in_correct_sequence(self):
        GradeLevel.initialize_defaults()
        codes = list(GradeLevel.objects.order_by("sequence_order").values_list("system_code", flat=True))
        expected = [
            "CRECHE", "PRE_NURSERY", "NURSERY_1", "NURSERY_2", "NURSERY_3",
            "BASIC_1", "BASIC_2", "BASIC_3", "BASIC_4", "BASIC_5", "BASIC_6",
            "JSS_1", "JSS_2", "JSS_3", "SS_1", "SS_2", "SS_3",
        ]
        self.assertEqual(codes, expected)
        nursery_3 = GradeLevel.objects.get(system_code="NURSERY_3")
        self.assertEqual(nursery_3.section, "PRE_PRIMARY")
        self.assertEqual(nursery_3.default_name, "Nursery 3")
        self.assertEqual(nursery_3.sequence_order, 5)
