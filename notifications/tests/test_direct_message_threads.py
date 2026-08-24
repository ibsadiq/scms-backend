from django_tenants.utils import schema_context

from academic.models import Student
from notifications.models import DirectMessage, Notification
from tenants.models import Client as SchoolTenant, Domain, TenantStatus
from users.models import CustomUser
from .support import MessagingTestCase


class DirectMessageThreadTests(MessagingTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with schema_context("public"):
            cls.other_tenant = SchoolTenant(
                schema_name="messaging_isolation_other", name="Other Messaging School",
                status=TenantStatus.ACTIVE,
            )
            cls.other_tenant.auto_create_schema = True
            cls.other_tenant.save(verbosity=0)
            cls.other_domain = Domain.objects.create(
                tenant=cls.other_tenant, domain="messaging-isolation-other.test.com",
                is_primary=True,
            )
        with schema_context(cls.other_tenant.schema_name):
            sender = CustomUser.objects.create_user(
                pk=800001, email="sender@other-messaging.test", password="x", is_admin=True,
            )
            recipient = CustomUser.objects.create_user(
                pk=800002, email="recipient@other-messaging.test", password="x", is_parent=True,
            )
            cls.foreign_message_id = DirectMessage.objects.create(
                pk=800001, sender=sender, recipient=recipient, body="Foreign",
            ).pk
            cls.foreign_user_id = recipient.pk
            cls.foreign_student_id = Student.objects.create(
                pk=800001, first_name="Foreign", last_name="Student",
                parent_contact="08097779999", admission_number="FOREIGN-1",
            ).pk

    @classmethod
    def tearDownClass(cls):
        try:
            with schema_context("public"):
                cls.other_domain.delete()
                cls.other_tenant.delete(force_drop=True)
        finally:
            super().tearDownClass()

    def test_valid_reply_preserves_participants_and_student(self):
        original = DirectMessage.objects.create(
            sender=self.teacher_user, recipient=self.parent_user,
            student=self.student, body="Original",
        )
        response = self.post_message(
            self.parent_user, self.teacher_user, parent_message=original,
        )
        self.assertEqual(response.status_code, 201)
        reply = DirectMessage.objects.get(pk=response.data["id"])
        self.assertEqual(reply.student, self.student)

    def test_reply_cannot_bridge_participants_or_student_context(self):
        original = DirectMessage.objects.create(
            sender=self.teacher_user, recipient=self.parent_user,
            student=self.student, body="Original",
        )
        self.assertEqual(
            self.post_message(self.parent_user, self.admin, parent_message=original).status_code,
            403,
        )
        self.assertEqual(
            self.post_message(
                self.parent_user, self.teacher_user, student=self.other_student,
                parent_message=original,
            ).status_code,
            403,
        )
        self.assertEqual(
            self.post_message(
                self.other_parent_user, self.teacher_user, parent_message=original,
            ).status_code,
            403,
        )

    def test_cross_tenant_parent_message_is_not_resolvable(self):
        self.client.force_authenticate(self.parent_user)
        response = self.client.post("/api/notifications/messages/", {
            "recipient": self.teacher_user.pk, "body": "No",
            "parent_message": self.foreign_message_id,
        }, format="json")
        self.assertEqual(response.status_code, 403)

    def test_cross_tenant_recipient_and_student_are_not_resolvable(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post("/api/notifications/messages/", {
            "recipient": self.foreign_user_id, "body": "No",
        }, format="json")
        self.assertEqual(response.status_code, 403)
        response = self.client.post("/api/notifications/messages/", {
            "recipient": self.parent_user.pk, "student": self.foreign_student_id,
            "body": "No",
        }, format="json")
        self.assertEqual(response.status_code, 403)
        response = self.client.get("/api/notifications/messages/school_admins/")
        self.assertNotIn(self.foreign_user_id, {row["user_id"] for row in response.data})

    def test_notification_is_created_once_after_commit(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post_message(self.teacher_user, self.parent_user, student=self.student)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Notification.objects.filter(
            idempotency_key=f'direct-message:{response.data["id"]}'
        ).count(), 1)
