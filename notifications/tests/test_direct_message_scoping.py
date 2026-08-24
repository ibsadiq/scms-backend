from django.urls import reverse

from notifications.models import DirectMessage
from .support import MessagingTestCase


class DirectMessageScopingTests(MessagingTestCase):
    def test_recipient_discovery_is_minimal_and_policy_scoped(self):
        self.client.force_authenticate(self.teacher_user)
        response = self.client.get(reverse("messages-recipients"))
        ids = {row["user_id"] for row in response.data}
        self.assertIn(self.admin.pk, ids)
        self.assertIn(self.parent_user.pk, ids)
        self.assertIn(self.student_user.pk, ids)
        self.assertNotIn(self.other_parent_user.pk, ids)
        self.assertNotIn(self.other_student_user.pk, ids)
        self.assertEqual(
            set(response.data[0]), {"user_id", "display_name", "role", "relationship"},
        )

        self.client.force_authenticate(self.parent_user)
        response = self.client.get(reverse("messages-recipients"))
        parent_ids = {row["user_id"] for row in response.data}
        self.assertEqual(parent_ids, {self.admin.pk, self.teacher_user.pk})

    def test_classroom_parent_enumeration_is_scoped_and_minimal(self):
        self.client.force_authenticate(self.teacher_user)
        response = self.client.get(reverse("messages-classroom-parents"))
        self.assertEqual({row["student_id"] for row in response.data}, {self.student.pk})
        self.assertEqual(set(response.data[0]), {
            "student_id", "student_name", "classroom", "parent_user_id", "parent_name",
        })
        response = self.client.get(
            reverse("messages-classroom-parents"), {"classroom_id": self.other_class.pk},
        )
        self.assertEqual(response.data, [])
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse("messages-classroom-parents"))
        self.assertEqual(
            {row["student_id"] for row in response.data},
            {self.student.pk, self.other_student.pk},
        )
        for actor in (self.parent_user, self.student_user, self.accountant, self.staff):
            self.client.force_authenticate(actor)
            self.assertEqual(
                self.client.get(reverse("messages-classroom-parents")).status_code, 403,
            )

    def test_school_admin_discovery_is_minimal_and_excludes_django_staff(self):
        self.client.force_authenticate(self.parent_user)
        response = self.client.get(reverse("messages-school-admins"))
        self.assertEqual({row["user_id"] for row in response.data}, {self.admin.pk})
        self.assertEqual(set(response.data[0]), {"user_id", "display_name", "role"})

    def test_messages_are_immutable(self):
        message = DirectMessage.objects.create(sender=self.teacher_user, recipient=self.parent_user, body="Original")
        self.client.force_authenticate(self.teacher_user)
        url = reverse("messages-detail", args=[message.pk])
        self.assertEqual(self.client.put(url, {"body": "Changed"}).status_code, 405)
        self.assertEqual(self.client.patch(url, {"body": "Changed"}).status_code, 405)
        self.assertEqual(self.client.delete(url).status_code, 405)
        message.refresh_from_db()
        self.assertEqual(message.body, "Original")

    def test_history_retrieve_and_read_state_are_participant_scoped(self):
        message = DirectMessage.objects.create(sender=self.teacher_user, recipient=self.parent_user, body="Read me")
        detail = reverse("messages-detail", args=[message.pk])
        self.client.force_authenticate(self.other_parent_user)
        self.assertEqual(self.client.get(detail).status_code, 404)
        self.client.force_authenticate(self.teacher_user)
        self.assertEqual(self.client.get(detail).status_code, 200)
        sent = self.client.get(reverse("messages-list"))
        self.assertIn(message.pk, {row["id"] for row in sent.data.get("results", sent.data)})
        self.assertEqual(self.client.post(reverse("messages-mark-read", args=[message.pk])).status_code, 403)
        self.client.force_authenticate(self.parent_user)
        received = self.client.get(reverse("messages-list"))
        self.assertIn(message.pk, {row["id"] for row in received.data.get("results", received.data)})
        mark_url = reverse("messages-mark-read", args=[message.pk])
        self.assertEqual(self.client.post(mark_url).status_code, 200)
        self.assertEqual(self.client.post(mark_url).status_code, 200)
        message.refresh_from_db()
        self.assertTrue(message.is_read)
