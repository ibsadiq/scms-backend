from .support import MessagingTestCase


class DirectMessageAuthorizationTests(MessagingTestCase):
    def test_admin_can_message_any_tenant_role(self):
        for recipient in (
            self.teacher_user, self.parent_user, self.student_user,
            self.accountant, self.staff,
        ):
            self.assertEqual(self.post_message(self.admin, recipient).status_code, 201)

    def test_teacher_matrix_and_student_context(self):
        for recipient, student in (
            (self.student_user, self.student),
            (self.parent_user, self.student),
            (self.admin, self.student),
        ):
            self.assertEqual(
                self.post_message(self.teacher_user, recipient, student=student).status_code,
                201,
            )
        for recipient, student in (
            (self.other_student_user, self.other_student),
            (self.other_parent_user, self.other_student),
        ):
            self.assertEqual(
                self.post_message(self.teacher_user, recipient, student=student).status_code,
                403,
            )

    def test_parent_matrix_and_child_context(self):
        self.assertEqual(
            self.post_message(self.parent_user, self.teacher_user, student=self.student).status_code,
            201,
        )
        self.assertEqual(self.post_message(self.parent_user, self.admin).status_code, 201)
        self.assertEqual(
            self.post_message(self.parent_user, self.other_teacher_user, student=self.student).status_code,
            403,
        )
        self.assertEqual(
            self.post_message(self.parent_user, self.teacher_user, student=self.other_student).status_code,
            403,
        )

    def test_student_matrix_and_self_context(self):
        self.assertEqual(
            self.post_message(self.student_user, self.teacher_user, student=self.student).status_code,
            201,
        )
        self.assertEqual(self.post_message(self.student_user, self.admin).status_code, 201)
        self.assertEqual(
            self.post_message(self.student_user, self.other_teacher_user, student=self.student).status_code,
            403,
        )
        self.assertEqual(
            self.post_message(self.student_user, self.teacher_user, student=self.other_student).status_code,
            403,
        )

    def test_accountant_and_ordinary_staff_can_only_message_admin(self):
        for sender in (self.accountant, self.staff):
            self.assertEqual(self.post_message(sender, self.admin).status_code, 201)
            for recipient in (self.teacher_user, self.parent_user, self.student_user):
                self.assertEqual(self.post_message(sender, recipient).status_code, 403)

