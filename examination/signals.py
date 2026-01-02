"""
Examination Signals - Marked Scripts Upload

Automatically trigger notifications for:
- Marked scripts uploaded by teachers
- Marked scripts made visible to students/parents
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import MarkedScript
from notifications.services import NotificationService

logger = logging.getLogger(__name__)
notification_service = NotificationService()


@receiver(post_save, sender=MarkedScript)
def notify_marked_script_upload(sender, instance, created, **kwargs):
    """
    Send notification when teacher uploads a marked script.

    Notifies:
    - Student (if visible_to_student is True)
    - Parent (if visible_to_parent is True)
    """
    if not created:
        # Check if visibility changed
        try:
            old_instance = MarkedScript.objects.get(pk=instance.pk)
            visibility_changed = (
                old_instance.visible_to_student != instance.visible_to_student or
                old_instance.visible_to_parent != instance.visible_to_parent
            )
            if not visibility_changed:
                return  # No visibility change, don't notify
        except MarkedScript.DoesNotExist:
            pass

    student = instance.student

    # Notify student if visible
    if instance.visible_to_student and student.user and student.can_login:
        try:
            notification_service.create_notification(
                recipient=student.user,
                notification_type='exam',
                title=f"Marked Script Available: {instance.exam.name}",
                message=f"Your marked script for {instance.subject.name} ({instance.exam.name}) "
                        f"has been uploaded by your teacher and is now available for viewing.",
                priority='normal',
                related_student=student,
                related_object=instance,
                send_email=True,
                send_sms=False
            )
            logger.info(f"Marked script notification sent to student {student.id}")
        except Exception as e:
            logger.error(f"Failed to send marked script notification to student {student.id}: {str(e)}")

    # Notify parent if visible
    if instance.visible_to_parent and student.parent_guardian and student.parent_guardian.user:
        try:
            notification_service.create_notification(
                recipient=student.parent_guardian.user,
                notification_type='exam',
                title=f"Marked Script for {student.full_name}",
                message=f"The marked script for {student.full_name}'s {instance.subject.name} "
                        f"exam ({instance.exam.name}) has been uploaded and is now available for viewing.",
                priority='normal',
                related_student=student,
                related_object=instance,
                send_email=True,
                send_sms=False
            )
            logger.info(f"Marked script notification sent to parent of student {student.id}")
        except Exception as e:
            logger.error(f"Failed to send marked script notification to parent: {str(e)}")
