from unittest.mock import patch
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from academic.models import Teacher, Staff
from school.testcases import TenantTestCase
from tenants.models import TenantStatus
from users.models import CustomUser, UserInvitation


class TeacherInvitationAndLastLoginTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        super().setup_tenant(tenant)
        tenant.name = "Teacher Invite Test School"
        tenant.status = TenantStatus.ACTIVE

    def setUp(self):
        self.client = APIClient(HTTP_HOST=self.domain.domain)
        self.admin = CustomUser.objects.create_user(
            email="admin@school.test",
            password="admin-password",
            is_admin=True,
            is_staff=True,
        )
        self.client.force_authenticate(user=self.admin)

        # Teacher who has never logged in
        self.teacher_user = CustomUser.objects.create_user(
            email="teacher.new@school.test",
            first_name="Jane",
            last_name="Doe",
            password="teacher-password",
            is_teacher=True,
        )
        self.teacher_user.last_login = None
        self.teacher_user.save()

        self.teacher = Teacher.objects.create(
            user=self.teacher_user,
            empId="TCH001",
        )

    def test_teacher_serializer_and_detail_exposes_last_login(self):
        response = self.client.get(f"/api/users/teachers/{self.teacher.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("last_login", response.data)
        self.assertIsNone(response.data["last_login"])

        # Now simulate login
        now = timezone.now()
        self.teacher_user.last_login = now
        self.teacher_user.save()

        response = self.client.get(f"/api/users/teachers/{self.teacher.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data["last_login"])

    @patch("core.email_utils.send_teacher_invitation")
    def test_resend_invitation_succeeds_when_no_last_login(self, mock_send):
        mock_send.return_value = True
        response = self.client.post(f"/api/users/teachers/{self.teacher.id}/resend-invitation/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("Invitation email sent successfully", response.data["message"])

        # Verify UserInvitation record was created
        invitation = UserInvitation.objects.get(email=self.teacher.email, role="teacher")
        self.assertEqual(invitation.status, "pending")
        self.assertEqual(invitation.teacher_profile_id, self.teacher.id)
        mock_send.assert_called_once()

    @patch("core.email_utils.send_teacher_invitation")
    def test_resend_invitation_reuses_and_renews_existing_pending_invitation(self, mock_send):
        mock_send.return_value = True
        # First send
        res1 = self.client.post(f"/api/users/teachers/{self.teacher.id}/resend-invitation/")
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        inv1 = UserInvitation.objects.get(email=self.teacher.email, role="teacher")

        # Second send
        res2 = self.client.post(f"/api/users/teachers/{self.teacher.id}/resend-invitation/")
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        inv2 = UserInvitation.objects.get(email=self.teacher.email, role="teacher")

        self.assertEqual(inv1.pk, inv2.pk)
        self.assertEqual(mock_send.call_count, 2)

    @patch("core.email_utils.send_teacher_invitation")
    def test_resend_invitation_rejected_when_teacher_has_last_login(self, mock_send):
        self.teacher_user.last_login = timezone.now()
        self.teacher_user.save()

        response = self.client.post(f"/api/users/teachers/{self.teacher.id}/resend-invitation/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already logged in", response.data["error"])
        mock_send.assert_not_called()
