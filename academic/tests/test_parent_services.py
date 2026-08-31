from django.core.exceptions import ValidationError

from school.testcases import TenantTestCase
from academic.models import Parent, Student
from academic.services.parent_identity_service import ParentIdentityService
from academic.services.parent_student_service import ParentStudentService
from users.models import CustomUser


class ParentIdentityServiceTests(TenantTestCase):
    def test_creates_parent_user_role_and_normalizes_phone(self):
        parent = ParentIdentityService.resolve_parent(
            phone_number="08012345678", email="Parent@Example.test",
            first_name="Ada", last_name="Okafor",
        )
        self.assertEqual(parent.phone_number, "+2348012345678")
        self.assertEqual(parent.user.phone_number, "+2348012345678")
        self.assertTrue(parent.user.is_parent)
        self.assertTrue(parent.user.groups.filter(name="parent").exists())

    def test_reuses_matching_user(self):
        user = CustomUser.objects.create_user(
            email="parent@example.test",
            password="test-password",
            phone_number="2348012345678",
        )
        parent = ParentIdentityService.resolve_parent(
            phone_number="08012345678", email="parent@example.test",
        )
        self.assertEqual(parent.user, user)

    def test_equivalent_phone_formats_resolve_same_parent(self):
        first = ParentIdentityService.resolve_parent(phone_number="08012345678", email="same@example.test")
        second = ParentIdentityService.resolve_parent(phone_number="2348012345678", email="same@example.test")
        self.assertEqual(first, second)

    def test_different_email_and_phone_identities_are_rejected(self):
        ParentIdentityService.resolve_parent(phone_number="08012345678", email="one@example.test")
        ParentIdentityService.resolve_parent(phone_number="08087654321", email="two@example.test")
        with self.assertRaises(ValidationError):
            ParentIdentityService.resolve_parent(phone_number="08012345678", email="two@example.test")

    def test_sync_user_and_reject_conflicts(self):
        parent = ParentIdentityService.resolve_parent(phone_number="08012345678", email="one@example.test")
        parent.email = "changed@example.test"
        parent.phone_number = "+2348087654321"
        parent.save()
        ParentIdentityService.sync_user(parent)
        parent.user.refresh_from_db()
        self.assertEqual(parent.user.email, "changed@example.test")
        self.assertEqual(parent.user.phone_number, "+2348087654321")
        CustomUser.objects.create_user(
            email="taken@example.test",
            password="test-password",
            phone_number="+2348099999999",
        )
        parent.email = "taken@example.test"
        with self.assertRaises(ValidationError):
            ParentIdentityService.sync_user(parent)


class ParentStudentServiceTests(TenantTestCase):
    def setUp(self):
        self.parent_a = Parent.objects.create(phone_number="+2348011111111", first_name="A")
        self.parent_b = Parent.objects.create(phone_number="+2348022222222", first_name="B")
        self.students = [
            Student.objects.create(first_name="Student", last_name=str(i), admission_number=f"S-{i}")
            for i in range(1, 4)
        ]

    def test_assign_one_and_multiple_students(self):
        ParentStudentService.sync_students(self.parent_a, [self.students[0].pk, self.students[1].pk])
        for student in self.students[:2]:
            student.refresh_from_db()
            self.assertEqual(student.parent_guardian, self.parent_a)
            self.assertEqual(student.parent_contact, self.parent_a.phone_number)

    def test_final_set_removes_one_and_empty_removes_all(self):
        ParentStudentService.sync_students(self.parent_a, [s.pk for s in self.students])
        ParentStudentService.sync_students(self.parent_a, [self.students[0].pk])
        self.students[1].refresh_from_db()
        self.assertIsNone(self.students[1].parent_guardian)
        self.assertIsNone(self.students[1].parent_contact)
        ParentStudentService.sync_students(self.parent_a, [])
        self.students[0].refresh_from_db()
        self.assertIsNone(self.students[0].parent_guardian)
        self.assertIsNone(self.students[0].parent_contact)

    def test_reassign_and_synchronize_contact(self):
        ParentStudentService.assign_parent(self.students[0], self.parent_a)
        ParentStudentService.assign_parent(self.students[0], self.parent_b)
        self.students[0].refresh_from_db()
        self.assertEqual(self.students[0].parent_guardian, self.parent_b)
        self.parent_b.phone_number = "+2348033333333"
        self.parent_b.save()
        ParentStudentService.synchronize_contact(self.parent_b)
        self.students[0].refresh_from_db()
        self.assertEqual(self.students[0].parent_contact, self.parent_b.phone_number)

    def test_invalid_student_ids_are_rejected(self):
        with self.assertRaises(ValidationError):
            ParentStudentService.sync_students(self.parent_a, [999999])

    def test_student_can_be_saved_unlinked(self):
        student = self.students[0]
        student.parent_guardian = None
        student.parent_contact = None
        student.save()
        student.refresh_from_db()
        self.assertIsNone(student.parent_guardian)
