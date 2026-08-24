from django.urls import reverse
from rest_framework.test import APIClient

from academic.models import Staff
from school.testcases import TenantTestCase
from tenants.models import TenantStatus
from users.models import CustomUser
from users.serializers import UserSerializer


class OrdinaryStaffRoleContractTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        super().setup_tenant(tenant)
        tenant.name = "Staff Role Contract School"
        tenant.status = TenantStatus.ACTIVE

    def setUp(self):
        self.password = "staff-role-test-password"
        self.user = CustomUser.objects.create_user(
            email="ordinary.staff@example.test",
            password=self.password,
        )
        self.staff = Staff.objects.create(
            user=self.user,
            role=Staff.Role.OTHER,
            designation="Office Assistant",
        )
        self.client = APIClient(HTTP_HOST=self.domain.domain)

    def test_active_staff_identity_resolves_to_staff(self):
        self.assertEqual(self.user.get_available_roles(), ["staff"])
        self.assertEqual(self.user.get_effective_role(), "staff")
        self.assertNotEqual(self.user.get_effective_role(), "admin")

    def test_login_profile_and_role_state_expose_staff(self):
        login = self.client.post(
            reverse("token_obtain_pair"),
            {"email": self.user.email, "password": self.password},
            format="json",
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.data["active_role"], "staff")
        self.assertEqual(login.data["available_roles"], ["staff"])

        self.client.force_authenticate(self.user)
        profile = self.client.get(reverse("users-profile"))
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.data["active_role"], "staff")
        self.assertEqual(profile.data["available_roles"], ["staff"])

        roles = self.client.get(reverse("user-roles"))
        self.assertEqual(roles.status_code, 200)
        self.assertEqual(roles.data["active_role"], "staff")
        self.assertEqual(roles.data["available_roles"], ["staff"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.active_role, "staff")

    def test_django_is_staff_alone_does_not_resolve_to_tenant_staff(self):
        django_staff = CustomUser.objects.create_user(
            email="django.staff.only@example.test",
            password=self.password,
            is_staff=True,
        )

        self.assertEqual(django_staff.get_available_roles(), [])
        self.assertIsNone(django_staff.get_effective_role())
        serialized = UserSerializer(django_staff).data
        self.assertIsNone(serialized["active_role"])
        self.assertEqual(serialized["available_roles"], [])

    def test_inactive_staff_identity_does_not_resolve_to_staff(self):
        self.staff.is_active = False
        self.staff.save(update_fields=["is_active"])

        self.assertEqual(self.user.get_available_roles(), [])
        self.assertIsNone(self.user.get_effective_role())

    def test_specialist_staff_identity_does_not_fall_back_to_ordinary_staff(self):
        self.staff.role = Staff.Role.ADMINISTRATOR
        self.staff.save(update_fields=["role"])

        self.assertEqual(self.user.get_available_roles(), [])
        self.assertIsNone(self.user.get_effective_role())

    def test_existing_specific_role_precedence_is_unchanged(self):
        role_flags = (
            ("admin", "is_admin"),
            ("teacher", "is_teacher"),
            ("parent", "is_parent"),
            ("student", "is_student"),
            ("accountant", "is_accountant"),
        )
        for index, (expected_role, flag) in enumerate(role_flags):
            with self.subTest(role=expected_role):
                actor = CustomUser.objects.create_user(
                    email=f"role-{index}@example.test",
                    password=self.password,
                    **{flag: True},
                )
                Staff.objects.create(user=actor, role=Staff.Role.OTHER)
                self.assertEqual(actor.get_available_roles(), [expected_role])
                self.assertEqual(actor.get_effective_role(), expected_role)
