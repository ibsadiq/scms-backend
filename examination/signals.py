"""Committed, transition-aware notifications for examination artifacts."""

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from notifications.services import NotificationService

from .models import MarkedScript


@receiver(pre_save, sender=MarkedScript)
def capture_marked_script_visibility(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_visibility = (False, False)
        return
    previous = MarkedScript.objects.filter(pk=instance.pk).values_list(
        "visible_to_student", "visible_to_parent"
    ).first()
    instance._previous_visibility = previous or (False, False)


@receiver(post_save, sender=MarkedScript)
def schedule_marked_script_notifications(sender, instance, created, **kwargs):
    was_student_visible, was_parent_visible = getattr(
        instance, "_previous_visibility", (False, False)
    )
    student_transition = instance.visible_to_student and not was_student_visible
    parent_transition = instance.visible_to_parent and not was_parent_visible
    if not student_transition and not parent_transition:
        return
    script_id = instance.pk
    transaction.on_commit(
        lambda: _notify_marked_script(
            script_id=script_id,
            notify_student=student_transition,
            notify_parent=parent_transition,
        )
    )


def _notify_marked_script(*, script_id, notify_student, notify_parent):
    script = MarkedScript.objects.select_related(
        "student__user", "student__parent_guardian__user", "exam", "subject"
    ).get(pk=script_id)
    student = script.student
    service = NotificationService()

    if notify_student and script.visible_to_student and student.user_id and student.can_login:
        service.create_notification(
            recipient=student.user,
            notification_type="exam",
            title=f"Marked Script Available: {script.exam.name}",
            message=(
                f"Your marked script for {script.subject.name} ({script.exam.name}) "
                "is now available for viewing."
            ),
            related_student=student,
            related_object=script,
            send_email=True,
            send_sms=False,
            idempotency_key=f"marked-script:{script.pk}:student-visible:{student.user_id}",
        )

    parent_user = student.parent_guardian.user if student.parent_guardian_id else None
    if notify_parent and script.visible_to_parent and parent_user:
        service.create_notification(
            recipient=parent_user,
            notification_type="exam",
            title=f"Marked Script for {student.full_name}",
            message=(
                f"The marked script for {student.full_name}'s {script.subject.name} "
                f"exam ({script.exam.name}) is now available for viewing."
            ),
            related_student=student,
            related_object=script,
            send_email=True,
            send_sms=False,
            idempotency_key=f"marked-script:{script.pk}:parent-visible:{parent_user.pk}",
        )
