from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from school.testcases import TenantTestCase

from academic.models import Staff, Teacher
from academic.services import StaffIdentityService


User = get_user_model()


class StaffIdentityTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        return super().setup_tenant(tenant)

    def test_teacher_creation_maps_to_staff_without_replacing_teacher_user(self):
        user = User.objects.create_user(email="teacher@example.com", password="test", is_teacher=True)
        staff = Staff.objects.create(
            user=user,
            role=Staff.Role.TEACHER,
            designation="Mathematics Teacher",
        )
        teacher = Teacher.objects.create(user=user, staff=staff)

        teacher.refresh_from_db()
        self.assertEqual(teacher.staff.user, user)
        self.assertEqual(teacher.staff.role, Staff.Role.TEACHER)
        self.assertEqual(teacher.staff.designation, "Mathematics Teacher")
        self.assertEqual(teacher.user, user)

    def test_non_teaching_staff_can_map_to_accountant_user(self):
        user = User.objects.create_user(email="accounts@example.com", password="test", is_accountant=True)
        staff, created = StaffIdentityService.ensure_for_user(user)

        self.assertTrue(created)
        self.assertEqual(staff.role, Staff.Role.ACCOUNTANT)
        self.assertFalse(hasattr(staff, "teacher_profile"))

    def test_service_prevents_duplicate_profile_for_same_user(self):
        user = User.objects.create_user(email="admin@example.com", password="test", is_admin=True)
        first, _ = StaffIdentityService.ensure_for_user(user)
        second, created = StaffIdentityService.ensure_for_user(user)

        self.assertFalse(created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Staff.objects.filter(user=user).count(), 1)

    def test_database_prevents_duplicate_profile_for_same_user(self):
        user = User.objects.create_user(email="duplicate@example.com", password="test")
        Staff.objects.create(user=user)
        with self.assertRaises((IntegrityError, ValidationError)):
            Staff.objects.create(user=user)
