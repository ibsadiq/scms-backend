from rest_framework.test import APIClient

from school.testcases import TenantTestCase
from academic.models import Parent, Student
from academic.services.parent_identity_service import ParentIdentityService
from users.models import CustomUser


class ParentAPITests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.status = "active"
        return super().setup_tenant(tenant)

    def setUp(self):
        self.admin = CustomUser.objects.create_user(email="admin@example.test", password="test", is_admin=True)
        self.client = APIClient(HTTP_HOST=self.domain.domain)
        self.client.force_authenticate(self.admin)

    def test_create_update_relationships_and_parent_type(self):
        first = Student.objects.create(first_name="One", last_name="Child", admission_number="API-1")
        second = Student.objects.create(first_name="Two", last_name="Child", admission_number="API-2")
        response = self.client.post("/api/users/parents/", {
            "first_name": "Pat", "last_name": "Ent", "email": "pat@example.test",
            "phone_number": "08012345678", "parent_type": "Guardian",
            "students": [first.pk, second.pk],
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        parent = Parent.objects.get(pk=response.data["id"])
        self.assertEqual(parent.parent_type, "Guardian")
        self.assertEqual({child["id"] for child in response.data["children"]}, {first.pk, second.pk})

        unchanged = self.client.patch(f"/api/users/parents/{parent.pk}/", {
            "email": parent.email, "phone_number": parent.phone_number,
            "occupation": "Engineer", "parent_type": "Father",
        }, format="json")
        self.assertEqual(unchanged.status_code, 200, unchanged.data)
        self.assertEqual(unchanged.data["parent_type"], "Father")
        self.assertEqual(parent.children.count(), 2)

        removed = self.client.patch(f"/api/users/parents/{parent.pk}/", {"students": [first.pk]}, format="json")
        self.assertEqual(removed.status_code, 200, removed.data)
        second.refresh_from_db()
        self.assertIsNone(second.parent_guardian)
        self.assertIsNone(second.parent_contact)

        empty = self.client.patch(f"/api/users/parents/{parent.pk}/", {"students": []}, format="json")
        self.assertEqual(empty.status_code, 200, empty.data)
        first.refresh_from_db()
        self.assertIsNone(first.parent_guardian)

    def test_phone_change_syncs_child_and_delete_clears_contact(self):
        parent = ParentIdentityService.resolve_parent(phone_number="08012345678", email="p@example.test")
        child = Student.objects.create(first_name="One", last_name="Child", admission_number="API-3", parent_guardian=parent, parent_contact=parent.phone_number)
        response = self.client.patch(f"/api/users/parents/{parent.pk}/", {"phone_number": "08087654321"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        child.refresh_from_db()
        self.assertEqual(child.parent_contact, "+2348087654321")
        response = self.client.delete(f"/api/users/parents/{parent.pk}/")
        self.assertEqual(response.status_code, 204)
        child.refresh_from_db()
        self.assertIsNone(child.parent_guardian)
        self.assertIsNone(child.parent_contact)

    def test_matching_user_is_reused_and_duplicate_parent_is_rejected(self):
        user = CustomUser.objects.create_user(
            email="existing@example.test", password="test-password",
            phone_number="+2348012345678",
        )
        payload = {
            "first_name": "Existing", "last_name": "User",
            "email": user.email, "phone_number": "08012345678",
        }
        response = self.client.post("/api/users/parents/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Parent.objects.get(pk=response.data["id"]).user, user)
        duplicate = self.client.post("/api/users/parents/", payload, format="json")
        self.assertEqual(duplicate.status_code, 400)

    def test_conflicting_email_and_phone_updates_are_rejected(self):
        first = ParentIdentityService.resolve_parent(phone_number="08011111111", email="one@example.test")
        second = ParentIdentityService.resolve_parent(phone_number="08022222222", email="two@example.test")
        email_conflict = self.client.patch(
            f"/api/users/parents/{first.pk}/", {"email": second.email}, format="json",
        )
        self.assertEqual(email_conflict.status_code, 400)
        phone_conflict = self.client.patch(
            f"/api/users/parents/{first.pk}/", {"phone_number": "2348022222222"}, format="json",
        )
        self.assertEqual(phone_conflict.status_code, 400)
