from django.db import transaction


class AttendanceNotificationService:
    ABSENT = "BECAME_ABSENT"
    RETURNED = "RETURNED_FROM_ABSENCE"

    @classmethod
    def schedule_transition(cls, *, student, attendance_date, was_absent, is_absent):
        if was_absent == is_absent:
            return
        transition = cls.ABSENT if is_absent else cls.RETURNED
        student_id = student.pk
        transaction.on_commit(
            lambda: cls._notify(
                student_id=student_id,
                attendance_date=attendance_date,
                transition=transition,
            )
        )

    @classmethod
    def _notify(cls, *, student_id, attendance_date, transition):
        from academic.models import Student
        from notifications.services import NotificationService

        student = Student.objects.select_related("user", "parent_guardian__user").get(pk=student_id)
        recipients = []
        if student.user_id and student.can_login:
            recipients.append(student.user)
        if student.parent_guardian and student.parent_guardian.user_id:
            recipients.append(student.parent_guardian.user)

        absent = transition == cls.ABSENT
        title = "Attendance absence recorded" if absent else "Attendance status updated"
        message = (
            f"{student.full_name} was marked absent on {attendance_date}."
            if absent else
            f"{student.full_name}'s attendance for {attendance_date} was updated from absent."
        )
        service = NotificationService()
        for recipient in recipients:
            service.create_notification(
                recipient=recipient,
                notification_type="attendance",
                title=title,
                message=message,
                priority="high" if absent else "normal",
                related_student=student,
                send_email=True,
                send_sms=False,
                idempotency_key=(
                    f"attendance:{student.pk}:{attendance_date.isoformat()}:{transition}:{recipient.pk}"
                ),
            )
