from rest_framework.test import APIClient

from school.testcases import TenantTestCase
from academic.models import Parent, Student, Teacher
from academic.services.parent_identity_service import ParentIdentityService
from academic.services.parent_student_service import ParentStudentService
from users.models import CustomUser, UserInvitation
from django.contrib.auth.models import Group
from django.contrib import admin
from django.core.exceptions import ValidationError


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

    def test_create_parent_without_email_and_without_invitation(self):
        from users.invitation_models import UserInvitation
        payload = {
            "first_name": "Solo",
            "last_name": "Parent",
            "phone_number": "08031112233",
            "send_invitation": False,
        }
        response = self.client.post("/api/users/parents/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(response.data["has_portal_account"])
        self.assertIsNone(response.data["invitation_status"])
        self.assertIsNone(response.data["email"])
        parent = Parent.objects.get(pk=response.data["id"])
        self.assertIsNone(parent.user)
        self.assertIsNone(parent.email)
        self.assertEqual(UserInvitation.objects.count(), 0)

    def test_create_parent_with_email_and_send_invitation_false(self):
        from users.invitation_models import UserInvitation
        payload = {
            "first_name": "Uninvited",
            "last_name": "Parent",
            "phone_number": "08032223344",
            "email": "guardian.uninvited@test.com",
            "send_invitation": False,
        }
        response = self.client.post("/api/users/parents/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(response.data["has_portal_account"])
        self.assertIsNone(response.data["invitation_status"])
        self.assertEqual(response.data["email"], "guardian.uninvited@test.com")
        self.assertEqual(UserInvitation.objects.filter(email="guardian.uninvited@test.com").count(), 0)

    from unittest.mock import patch

    @patch("core.email_utils.send_parent_invitation")
    def test_create_parent_with_email_and_send_invitation_true(self, send_invitation):
        from users.invitation_models import UserInvitation
        payload = {
            "first_name": "Invited",
            "last_name": "Parent",
            "phone_number": "08033334455",
            "email": "guardian.invited@test.com",
            "send_invitation": True,
        }
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/users/parents/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(UserInvitation.objects.filter(email="guardian.invited@test.com").count(), 1)
        send_invitation.assert_called_once()

    def test_send_invitation_true_without_email_rejected(self):
        payload = {
            "first_name": "NoEmail",
            "last_name": "Parent",
            "phone_number": "08034445566",
            "send_invitation": True,
        }
        response = self.client.post("/api/users/parents/", payload, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("email", str(response.data).lower())

    def test_existing_phone_only_parent_can_later_receive_email(self):
        from users.invitation_models import UserInvitation
        parent = Parent.objects.create(
            first_name="PhoneOnly",
            last_name="Guardian",
            phone_number="+2348035556677",
        )
        self.assertIsNone(parent.email)
        self.assertIsNone(parent.user)

        response = self.client.patch(f"/api/users/parents/{parent.pk}/", {
            "email": "later.email@test.com",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        parent.refresh_from_db()
        self.assertEqual(parent.email, "later.email@test.com")
        self.assertEqual(UserInvitation.objects.count(), 0)

    @patch("core.email_utils.send_parent_invitation")
    def test_send_invitation_to_existing_parent_with_email(self, send_invitation):
        from users.invitation_models import UserInvitation
        parent = Parent.objects.create(
            first_name="Existing",
            last_name="Parent",
            phone_number="+2348036667788",
            email="existing.parent@test.com",
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f"/api/users/parents/{parent.pk}/resend-invitation/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["invitation_status"], "PENDING")
        self.assertEqual(UserInvitation.objects.filter(email="existing.parent@test.com").count(), 1)
        send_invitation.assert_called_once()

    @patch("core.email_utils.send_parent_invitation")
    def test_resend_does_not_duplicate_pending_user_invitation(self, send_invitation):
        from users.invitation_models import UserInvitation
        parent = Parent.objects.create(
            first_name="Dedupe",
            last_name="Parent",
            phone_number="+2348037778899",
            email="dedupe.parent@test.com",
        )
        with self.captureOnCommitCallbacks(execute=True):
            res1 = self.client.post(f"/api/users/parents/{parent.pk}/resend-invitation/")
        self.assertEqual(res1.status_code, 200)

        with self.captureOnCommitCallbacks(execute=True):
            res2 = self.client.post(f"/api/users/parents/{parent.pk}/resend-invitation/")
        self.assertEqual(res2.status_code, 200)

        self.assertEqual(
            UserInvitation.objects.filter(email="dedupe.parent@test.com", status="pending").count(),
            1,
        )

    def test_active_portal_account_represented_correctly(self):
        user = CustomUser.objects.create_user(
            email="active.parent@test.com",
            password="real-password123",
            phone_number="+2348038889900",
            is_parent=True,
        )
        parent = Parent.objects.create(
            user=user,
            first_name="Active",
            last_name="Parent",
            phone_number=user.phone_number,
            email=user.email,
        )
        response = self.client.get(f"/api/users/parents/{parent.pk}/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["has_portal_account"])
        self.assertEqual(response.data["invitation_status"], "ACCEPTED")

        # Attempt to reinvite an active account
        resend = self.client.post(f"/api/users/parents/{parent.pk}/resend-invitation/")
        self.assertEqual(resend.status_code, 400)
        self.assertIn("active", str(resend.data).lower())

    def test_identity_collision_rejected_on_resend(self):
        from users.invitation_models import UserInvitation
        # User B exists with email taken@example.test and phone B
        CustomUser.objects.create_user(
            email="taken@example.test",
            phone_number="+2348030009999",
            password="password123",
            is_parent=True,
        )
        # Parent A has phone A and email taken@example.test, no user attached yet
        parent_a = Parent.objects.create(
            first_name="Colliding",
            last_name="Parent",
            phone_number="+2348030001111",
            email="taken@example.test",
            user=None,
        )

        response = self.client.post(f"/api/users/parents/{parent_a.pk}/resend-invitation/")
        self.assertEqual(response.status_code, 400)
        parent_a.refresh_from_db()
        self.assertIsNone(parent_a.user)
        self.assertEqual(UserInvitation.objects.filter(email="taken@example.test").count(), 0)

    def test_identity_mismatch_during_create_rejected(self):
        CustomUser.objects.create_user(
            email="user.identity@test.com",
            phone_number="+2348030008888",
            password="password123",
            is_parent=True,
        )
        payload = {
            "first_name": "Mismatch",
            "last_name": "Parent",
            "phone_number": "08037776666",
            "email": "user.identity@test.com",
            "send_invitation": False,
        }
        response = self.client.post("/api/users/parents/", payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_parent_serializer_exposes_correct_portal_status(self):
        parent = Parent.objects.create(
            first_name="StatusTest",
            last_name="Parent",
            phone_number="+2348031212121",
        )
        res = self.client.get(f"/api/users/parents/{parent.pk}/")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data["has_portal_account"])
        self.assertIsNone(res.data["invitation_status"])
        self.assertIsNone(res.data["last_login"])

    def test_student_detail_exposes_linked_guardian_email(self):
        parent = Parent.objects.create(
            first_name="Fatima",
            last_name="Ali",
            phone_number="+2348099887766",
            email="fatima.ali@test.com",
        )
        student = Student.objects.create(
            first_name="Zainab",
            last_name="Ali",
            admission_number="STD-001",
            parent_guardian=parent,
            parent_contact=parent.phone_number,
        )
        response = self.client.get(f"/api/sis/students/{student.pk}/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["parent_email"], "fatima.ali@test.com")
        self.assertEqual(response.data["parent_first_name"], "Fatima")
        self.assertEqual(response.data["parent_last_name"], "Ali")

    def test_student_without_guardian_gives_parent_email_null(self):
        student = Student.objects.create(
            first_name="Solo",
            last_name="Child",
            admission_number="STD-002",
            parent_guardian=None,
            parent_contact=None,
        )
        response = self.client.get(f"/api/sis/students/{student.pk}/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data["parent_email"])
        self.assertIsNone(response.data["parent_first_name"])
        self.assertIsNone(response.data["parent_last_name"])

    def test_student_with_guardian_without_email_gives_parent_email_null(self):
        parent = Parent.objects.create(
            first_name="NoEmail",
            last_name="Guardian",
            phone_number="+2348099112233",
            email=None,
        )
        student = Student.objects.create(
            first_name="Child",
            last_name="Guardian",
            admission_number="STD-003",
            parent_guardian=parent,
            parent_contact=parent.phone_number,
        )
        response = self.client.get(f"/api/sis/students/{student.pk}/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data["parent_email"])
        self.assertEqual(response.data["parent_first_name"], "NoEmail")
        self.assertEqual(response.data["parent_last_name"], "Guardian")

    def test_delete_parent_without_user_succeeds(self):
        parent = Parent.objects.create(
            first_name="NoUser",
            last_name="Parent",
            phone_number="+2348011002200",
            email=None,
            user=None,
        )
        response = self.client.delete(f"/api/users/parents/{parent.pk}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Parent.objects.filter(pk=parent.pk).exists())

    def test_delete_parent_only_user_clears_parent_role(self):
        user = CustomUser.objects.create_user(
            email="parentonly@test.com",
            phone_number="+2348011003300",
            password="pass",
            is_parent=True,
            active_role="parent",
        )
        group, _ = Group.objects.get_or_create(name="parent")
        user.groups.add(group)
        parent = Parent.objects.create(
            user=user,
            first_name="Parent",
            last_name="Only",
            phone_number="+2348011003300",
            email="parentonly@test.com",
        )
        response = self.client.delete(f"/api/users/parents/{parent.pk}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Parent.objects.filter(pk=parent.pk).exists())
        user.refresh_from_db()
        self.assertFalse(user.is_parent)
        self.assertFalse(user.is_active)
        self.assertNotIn("parent", list(user.groups.values_list("name", flat=True)))
        self.assertNotEqual(user.active_role, "parent")

    def test_delete_parent_clears_student_guardian_and_contact(self):
        parent = Parent.objects.create(
            first_name="Guarded",
            last_name="Parent",
            phone_number="+2348011004400",
            email="guarded@test.com",
        )
        child = Student.objects.create(
            first_name="Child",
            last_name="Guarded",
            admission_number="STD-DEL-1",
            parent_guardian=parent,
            parent_contact=parent.phone_number,
        )
        response = self.client.delete(f"/api/users/parents/{parent.pk}/")
        self.assertEqual(response.status_code, 204)
        child.refresh_from_db()
        self.assertIsNone(child.parent_guardian)
        self.assertIsNone(child.parent_contact)

    def test_delete_parent_invalidates_pending_invitation(self):
        parent = Parent.objects.create(
            first_name="Invited",
            last_name="Parent",
            phone_number="+2348011005500",
            email="invited.parent@test.com",
        )
        invitation = UserInvitation.objects.create(
            email="invited.parent@test.com",
            first_name="Invited",
            last_name="Parent",
            role="parent",
            status="pending",
            parent_profile_id=parent.pk,
            invited_by=self.admin,
        )
        response = self.client.delete(f"/api/users/parents/{parent.pk}/")
        self.assertEqual(response.status_code, 204)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "expired")

    def test_delete_parent_preserves_historical_accepted_invitation(self):
        parent = Parent.objects.create(
            first_name="Accepted",
            last_name="Parent",
            phone_number="+2348011006600",
            email="accepted.parent@test.com",
        )
        invitation = UserInvitation.objects.create(
            email="accepted.parent@test.com",
            first_name="Accepted",
            last_name="Parent",
            role="parent",
            status="accepted",
            parent_profile_id=parent.pk,
            invited_by=self.admin,
        )
        response = self.client.delete(f"/api/users/parents/{parent.pk}/")
        self.assertEqual(response.status_code, 204)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "accepted")

    def test_delete_parent_with_teacher_user_preserves_teacher(self):
        user = CustomUser.objects.create_user(
            email="teacherparent@test.com",
            phone_number="+2348011007700",
            password="pass",
            is_parent=True,
            is_teacher=True,
            is_active=True,
            active_role="teacher",
        )
        teacher_grp, _ = Group.objects.get_or_create(name="teacher")
        parent_grp, _ = Group.objects.get_or_create(name="parent")
        user.groups.add(teacher_grp, parent_grp)
        teacher = Teacher.objects.create(user=user, empId="TCHD001")
        parent = Parent.objects.create(
            user=user,
            first_name="Teacher",
            last_name="Parent",
            phone_number="+2348011007700",
            email="teacherparent@test.com",
        )
        response = self.client.delete(f"/api/users/parents/{parent.pk}/")
        self.assertEqual(response.status_code, 204)
        self.assertTrue(Teacher.objects.filter(pk=teacher.pk).exists())
        user.refresh_from_db()
        self.assertTrue(user.is_teacher)
        self.assertFalse(user.is_parent)
        self.assertTrue(user.is_active)
        self.assertIn("teacher", list(user.groups.values_list("name", flat=True)))
        self.assertNotIn("parent", list(user.groups.values_list("name", flat=True)))

    def test_delete_parent_with_other_role_keeps_user_active(self):
        user = CustomUser.objects.create_user(
            email="adminparent@test.com",
            phone_number="+2348011008800",
            password="pass",
            is_parent=True,
            is_admin=True,
            is_active=True,
        )
        parent = Parent.objects.create(
            user=user,
            first_name="Admin",
            last_name="Parent",
            phone_number="+2348011008800",
            email="adminparent@test.com",
        )
        response = self.client.delete(f"/api/users/parents/{parent.pk}/")
        self.assertEqual(response.status_code, 204)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_parent)

    def test_admin_parent_delete_uses_same_lifecycle(self):
        from sis.admin import ParentAdmin
        user = CustomUser.objects.create_user(
            email="admindel@test.com",
            phone_number="+2348011009900",
            password="pass",
            is_parent=True,
        )
        parent = Parent.objects.create(
            user=user,
            first_name="AdminDel",
            last_name="Parent",
            phone_number="+2348011009900",
            email="admindel@test.com",
        )
        child = Student.objects.create(
            first_name="Child",
            last_name="Del",
            admission_number="STD-DEL-ADM",
            parent_guardian=parent,
            parent_contact=parent.phone_number,
        )
        parent_admin = ParentAdmin(Parent, admin.site)
        parent_admin.delete_model(None, parent)
        self.assertFalse(Parent.objects.filter(pk=parent.pk).exists())
        user.refresh_from_db()
        self.assertFalse(user.is_parent)
        self.assertFalse(user.is_active)
        child.refresh_from_db()
        self.assertIsNone(child.parent_guardian)

    def test_admin_bulk_parent_delete_uses_same_lifecycle(self):
        from sis.admin import ParentAdmin
        p1 = Parent.objects.create(first_name="P1", last_name="Del", phone_number="+2348011010001", email="p1@test.com")
        p2 = Parent.objects.create(first_name="P2", last_name="Del", phone_number="+2348011010002", email="p2@test.com")
        parent_admin = ParentAdmin(Parent, admin.site)
        parent_admin.delete_queryset(None, Parent.objects.filter(pk__in=[p1.pk, p2.pk]))
        self.assertFalse(Parent.objects.filter(pk__in=[p1.pk, p2.pk]).exists())

    def test_orphan_parent_user_is_recovered(self):
        user = CustomUser.objects.create_user(
            email="orphan.recov@test.com",
            phone_number="+2348011020000",
            password="pass",
            is_parent=True,
        )
        parent = ParentIdentityService.resolve_parent(
            phone_number="08011020000",
            email="orphan.recov@test.com",
            first_name="Recovered",
            last_name="Parent",
        )
        self.assertEqual(parent.user, user)
        self.assertEqual(CustomUser.objects.filter(email="orphan.recov@test.com").count(), 1)
        user.refresh_from_db()
        self.assertTrue(user.is_parent)
        self.assertTrue(user.is_active)
        self.assertIn("parent", list(user.groups.values_list("name", flat=True)))

    def test_deleted_parent_can_be_recreated_using_same_user(self):
        parent = ParentIdentityService.resolve_parent(
            phone_number="08011030000",
            email="reborn@test.com",
            first_name="Original",
            last_name="Parent",
        )
        user = parent.user
        self.assertIsNotNone(user)
        ParentStudentService.delete_parent(parent)
        user.refresh_from_db()
        self.assertFalse(user.is_parent)
        self.assertFalse(user.is_active)

        reborn = ParentIdentityService.resolve_parent(
            phone_number="08011030000",
            email="reborn@test.com",
            first_name="Reborn",
            last_name="Parent",
        )
        self.assertEqual(reborn.user, user)
        user.refresh_from_db()
        self.assertTrue(user.is_parent)
        self.assertTrue(user.is_active)
        self.assertEqual(CustomUser.objects.filter(email="reborn@test.com").count(), 1)

    def test_orphan_user_conflicting_phone_is_rejected(self):
        CustomUser.objects.create_user(
            email="orphan.conflict@test.com",
            phone_number="+2348011040001",
            password="pass",
            is_parent=True,
        )
        with self.assertRaises(ValidationError):
            ParentIdentityService.resolve_parent(
                phone_number="08011040002",
                email="orphan.conflict@test.com",
            )

    def test_phone_and_email_resolving_to_different_users_is_rejected(self):
        CustomUser.objects.create_user(
            email="diff.a@test.com",
            phone_number="+2348011050001",
            password="pass",
        )
        CustomUser.objects.create_user(
            email="diff.b@test.com",
            phone_number="+2348011050002",
            password="pass",
        )
        with self.assertRaises(ValidationError):
            ParentIdentityService.resolve_parent(
                phone_number="08011050001",
                email="diff.b@test.com",
            )

    def test_phone_normalization_still_reuses_identity(self):
        user = CustomUser.objects.create_user(
            email="norm.phone@test.com",
            phone_number="+2348011060000",
            password="pass",
        )
        parent = ParentIdentityService.resolve_parent(
            phone_number="08011060000",
            email="norm.phone@test.com",
        )
        self.assertEqual(parent.user, user)

    def test_parent_without_user_gets_user_when_email_added(self):
        parent = Parent.objects.create(
            first_name="NoUser",
            last_name="Parent",
            phone_number="+2348011070000",
            email=None,
            user=None,
        )
        response = self.client.patch(
            f"/api/users/parents/{parent.pk}/",
            {"email": "added.user@test.com"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        parent.refresh_from_db()
        self.assertIsNotNone(parent.user)
        self.assertEqual(parent.user.email, "added.user@test.com")
        self.assertTrue(parent.user.is_parent)

    def test_parent_email_update_reuses_existing_unambiguous_user(self):
        user = CustomUser.objects.create_user(
            email="reuse.target@test.com",
            phone_number="+2348011080000",
            password="pass",
        )
        parent = Parent.objects.create(
            first_name="NeedsUser",
            last_name="Parent",
            phone_number="+2348011080000",
            email=None,
            user=None,
        )
        response = self.client.patch(
            f"/api/users/parents/{parent.pk}/",
            {"email": "reuse.target@test.com"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        parent.refresh_from_db()
        self.assertEqual(parent.user, user)
        self.assertEqual(CustomUser.objects.filter(email="reuse.target@test.com").count(), 1)

    def test_parent_email_update_rejects_identity_collision(self):
        CustomUser.objects.create_user(
            email="collide.target@test.com",
            phone_number="+2348011090001",
            password="pass",
        )
        parent = Parent.objects.create(
            first_name="Colliding",
            last_name="Parent",
            phone_number="+2348011090002",
            email=None,
            user=None,
        )
        response = self.client.patch(
            f"/api/users/parents/{parent.pk}/",
            {"email": "collide.target@test.com"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        parent.refresh_from_db()
        self.assertIsNone(parent.user)

    def test_accepting_invitation_for_deleted_parent_is_rejected(self):
        parent = Parent.objects.create(
            first_name="Ghost",
            last_name="Parent",
            phone_number="+2348011100000",
            email="ghost@test.com",
        )
        invitation = UserInvitation.objects.create(
            email="ghost@test.com",
            first_name="Ghost",
            last_name="Parent",
            role="parent",
            status="pending",
            parent_profile_id=parent.pk,
            invited_by=self.admin,
        )
        ParentStudentService.delete_parent(parent)
        payload = {
            "token": invitation.token,
            "password": "secure-password-123",
            "password_confirm": "secure-password-123",
        }
        response = self.client.post("/api/users/invitations/accept/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(CustomUser.objects.filter(email="ghost@test.com", is_parent=True, is_active=True).exists())

    def test_deleting_parent_does_not_delete_customuser(self):
        parent = ParentIdentityService.resolve_parent(
            phone_number="08011110000",
            email="keepuser@test.com",
            first_name="Keep",
            last_name="User",
        )
        user_pk = parent.user.pk
        response = self.client.delete(f"/api/users/parents/{parent.pk}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Parent.objects.filter(pk=parent.pk).exists())
        self.assertTrue(CustomUser.objects.filter(pk=user_pk).exists())


class ParentIdentityServiceTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.status = "active"
        return super().setup_tenant(tenant)

    def test_case_a_phone_user_a_email_user_b_raises_validation_error(self):
        from django.core.exceptions import ValidationError
        CustomUser.objects.create_user(
            email="user.a@test.com",
            phone_number="+2348031111111",
            password="pass",
            is_parent=True,
        )
        CustomUser.objects.create_user(
            email="user.b@test.com",
            phone_number="+2348032222222",
            password="pass",
            is_parent=True,
        )
        with self.assertRaises(ValidationError):
            ParentIdentityService.resolve_parent(
                phone_number="08031111111",
                email="user.b@test.com",
            )

    def test_case_b_phone_parent_a_email_user_b_raises_validation_error(self):
        from django.core.exceptions import ValidationError
        Parent.objects.create(
            first_name="Parent",
            last_name="A",
            phone_number="+2348033333333",
            email=None,
        )
        CustomUser.objects.create_user(
            email="user.b2@test.com",
            phone_number="+2348034444444",
            password="pass",
            is_parent=True,
        )
        with self.assertRaises(ValidationError):
            ParentIdentityService.resolve_parent(
                phone_number="08033333333",
                email="user.b2@test.com",
            )

    def test_case_c_phone_and_email_match_same_user_reuses_user(self):
        user = CustomUser.objects.create_user(
            email="same.user@test.com",
            phone_number="+2348035555555",
            password="pass",
            is_parent=True,
        )
        parent = ParentIdentityService.resolve_parent(
            phone_number="08035555555",
            email="same.user@test.com",
            first_name="Same",
            last_name="User",
        )
        self.assertEqual(parent.user, user)
        self.assertEqual(CustomUser.objects.filter(email="same.user@test.com").count(), 1)

    def test_case_d_phone_only_parent_later_gains_compatible_email_reuses_parent(self):
        parent = Parent.objects.create(
            first_name="Initial",
            last_name="PhoneOnly",
            phone_number="+2348036666666",
            email=None,
        )
        resolved = ParentIdentityService.resolve_parent(
            phone_number="08036666666",
            email="new.email@test.com",
            first_name="Initial",
            last_name="PhoneOnly",
        )
        self.assertEqual(resolved.pk, parent.pk)
        self.assertEqual(resolved.email, "new.email@test.com")
        self.assertIsNotNone(resolved.user)
        self.assertEqual(resolved.user.email, "new.email@test.com")

    def test_case_e_normalized_phone_variants_treated_as_same_identity(self):
        user = CustomUser.objects.create_user(
            email="variant.user@test.com",
            phone_number="+2348037777777",
            password="pass",
            is_parent=True,
        )
        parent = ParentIdentityService.resolve_parent(
            phone_number="08037777777",
            email="variant.user@test.com",
        )
        self.assertEqual(parent.user, user)



