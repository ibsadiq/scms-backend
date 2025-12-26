"""
Notification Signals - Phase 1.5: Automated Notifications System

Automatically trigger notifications for key events:
- Attendance alerts (student absent)
- Fee reminders (payment overdue)
- Result published (exam results available)
- Upcoming exams
- School events
- Promotion decisions
- Report cards available
"""
import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta

from attendance.models import StudentAttendance
# from finance.models import DebtRecord  # TODO: Update when debt tracking is implemented
from examination.models import TermResult, ReportCard
from academic.models import StudentPromotion
from administration.models import SchoolEvent

from .services import NotificationService
from .models import Notification

logger = logging.getLogger(__name__)
notification_service = NotificationService()


@receiver(post_save, sender=StudentAttendance)
def notify_attendance_alert(sender, instance, created, **kwargs):
    """
    Send notification when student is marked absent.

    Notifies parents when their child is absent.
    """
    if not created:
        return  # Only for new records

    # Check if status indicates absence
    if instance.status and not instance.status.absent:
        return  # Only for absences

    student = instance.student
    if not student.parent_guardian:
        return  # No parent to notify

    parent_user = student.parent_guardian.user

    try:
        notification_service.create_notification(
            recipient=parent_user,
            notification_type='attendance',
            title=f"Attendance Alert: {student.full_name}",
            message=f"{student.full_name} was marked absent on {instance.date.strftime('%B %d, %Y')}. "
                    f"If this is unexpected, please contact the school.",
            priority='high',
            related_student=student,
            related_object=instance,
            send_email=True,
            send_sms=False
        )
        logger.info(f"Attendance alert sent for student {student.id}")
    except Exception as e:
        logger.error(f"Failed to send attendance notification: {str(e)}")


# TODO: Re-enable when DebtRecord model is available
# @receiver(post_save, sender=DebtRecord)
# def notify_fee_reminder(sender, instance, created, **kwargs):
#     """
#     Send notification for fee payment reminders.
#
#     Notifies parents about outstanding fees.
#     """
#     if not created:
#         return  # Only for new debt records
#
#     student = instance.student
#     if not student.parent_guardian:
#         return
#
#     parent_user = student.parent_guardian.user
#
#     # Determine priority based on amount and time overdue
#     priority = 'normal'
#     if instance.remaining_balance > 50000:  # Large amount
#         priority = 'high'
#
#     try:
#         notification_service.create_notification(
#             recipient=parent_user,
#             notification_type='fee',
#             title=f"Fee Reminder: {student.full_name}",
#             message=f"Outstanding fee balance for {student.full_name}: "
#                     f"₦{instance.remaining_balance:,.2f}. "
#                     f"Term: {instance.term}. "
#                     f"Please make payment at your earliest convenience.",
#             priority=priority,
#             related_student=student,
#             related_object=instance,
#             send_email=True,
#             send_sms=priority == 'high'  # SMS only for high priority
#         )
#         logger.info(f"Fee reminder sent for student {student.id}")
#     except Exception as e:
#         logger.error(f"Failed to send fee notification: {str(e)}")


@receiver(post_save, sender=TermResult)
def notify_result_published(sender, instance, created, **kwargs):
    """
    Send notification when exam results are published.

    Notifies parents when their child's results are ready.
    """
    if not created:
        return

    student = instance.student
    if not student.parent_guardian:
        return

    parent_user = student.parent_guardian.user

    # Calculate performance indicator
    performance = "excellent" if instance.annual_average >= 75 else \
                  "good" if instance.annual_average >= 60 else \
                  "satisfactory" if instance.annual_average >= 50 else \
                  "needs improvement"

    try:
        notification_service.create_notification(
            recipient=parent_user,
            notification_type='result',
            title=f"Results Published: {student.full_name}",
            message=f"{student.full_name}'s {instance.term} results are now available. "
                    f"Annual Average: {instance.annual_average:.1f}%. "
                    f"Performance: {performance}. "
                    f"Log in to view detailed results.",
            priority='normal',
            related_student=student,
            related_object=instance,
            send_email=True,
            send_sms=False
        )
        logger.info(f"Result notification sent for student {student.id}")
    except Exception as e:
        logger.error(f"Failed to send result notification: {str(e)}")


@receiver(post_save, sender=ReportCard)
def notify_report_card_available(sender, instance, created, **kwargs):
    """
    Send notification when report card is generated.

    Notifies parents that report card is ready for download.
    """
    if not created:
        return

    student = instance.student
    if not student.parent_guardian:
        return

    parent_user = student.parent_guardian.user

    try:
        notification_service.create_notification(
            recipient=parent_user,
            notification_type='report_card',
            title=f"Report Card Available: {student.full_name}",
            message=f"{student.full_name}'s report card for {instance.term} ({instance.academic_year}) "
                    f"is now available. Log in to view and download the report card.",
            priority='normal',
            related_student=student,
            related_object=instance,
            send_email=True,
            send_sms=False
        )
        logger.info(f"Report card notification sent for student {student.id}")
    except Exception as e:
        logger.error(f"Failed to send report card notification: {str(e)}")


@receiver(post_save, sender=StudentPromotion)
def notify_promotion_decision(sender, instance, created, **kwargs):
    """
    Send notification when promotion decision is made.

    Notifies parents about promotion/repetition decisions.
    """
    if not created:
        return

    student = instance.student
    if not student.parent_guardian:
        return

    parent_user = student.parent_guardian.user

    # Build message based on status
    if instance.status == 'promoted':
        title = f"Promotion: {student.full_name}"
        message = f"Congratulations! {student.full_name} has been promoted from {instance.from_class} to {instance.to_class} " \
                  f"for the {instance.academic_year} academic year."
        priority = 'normal'
    elif instance.status == 'repeated':
        title = f"Class Repetition: {student.full_name}"
        message = f"{student.full_name} will be repeating {instance.from_class} in the {instance.academic_year} academic year. " \
                  f"Reason: {instance.reason or 'Academic performance'}. " \
                  f"Please schedule a meeting with the class teacher to discuss."
        priority = 'high'
    elif instance.status == 'graduated':
        title = f"Graduation: {student.full_name}"
        message = f"Congratulations! {student.full_name} has successfully completed {instance.from_class} " \
                  f"and graduated in the {instance.academic_year} academic year."
        priority = 'normal'
    elif instance.status == 'conditional':
        title = f"Conditional Promotion: {student.full_name}"
        message = f"{student.full_name} has been conditionally promoted from {instance.from_class} to {instance.to_class}. " \
                  f"Conditions: {instance.conditions or 'To be discussed with class teacher'}. " \
                  f"Please ensure conditions are met."
        priority = 'high'
    else:
        return  # Unknown status

    try:
        notification_service.create_notification(
            recipient=parent_user,
            notification_type='promotion',
            title=title,
            message=message,
            priority=priority,
            related_student=student,
            related_object=instance,
            send_email=True,
            send_sms=priority == 'high'  # SMS for high priority
        )
        logger.info(f"Promotion notification sent for student {student.id}")
    except Exception as e:
        logger.error(f"Failed to send promotion notification: {str(e)}")


@receiver(post_save, sender=SchoolEvent)
def notify_school_event(sender, instance, created, **kwargs):
    """
    Send notification for upcoming school events.

    Notifies all relevant users about school events.
    """
    if not created:
        return

    # Only notify for future events
    if instance.date < timezone.now().date():
        return

    # Determine if event is urgent (within 3 days)
    days_until_event = (instance.date - timezone.now().date()).days
    priority = 'urgent' if days_until_event <= 3 else 'normal'

    # Build recipient list based on event audience
    from users.models import CustomUser
    from academic.models import Parent

    recipients = []

    # If event is for all or parents, notify all parents
    if hasattr(instance, 'audience') and instance.audience in ['all', 'parents']:
        parent_users = CustomUser.objects.filter(parent__isnull=False)
        recipients.extend(parent_users)

    # If event is for teachers, notify all teachers
    if hasattr(instance, 'audience') and instance.audience in ['all', 'teachers']:
        teacher_users = CustomUser.objects.filter(teacher__isnull=False)
        recipients.extend(teacher_users)

    # If no specific audience, notify everyone
    if not hasattr(instance, 'audience') or instance.audience == 'all':
        recipients = CustomUser.objects.filter(is_active=True)

    # Remove duplicates
    recipients = list(set(recipients))

    if not recipients:
        return

    try:
        notification_service.send_bulk_notifications(
            recipients=recipients,
            notification_type='event',
            title=f"School Event: {instance.title}",
            message=f"{instance.title} on {instance.date.strftime('%B %d, %Y')}. "
                    f"{instance.description if hasattr(instance, 'description') else ''}",
            priority=priority,
            send_email=True,
            send_sms=False
        )
        logger.info(f"Event notifications sent for event {instance.id} to {len(recipients)} recipients")
    except Exception as e:
        logger.error(f"Failed to send event notifications: {str(e)}")


# TODO: Re-enable when DebtRecord model is available
# # Helper function to manually trigger fee reminders for overdue debts
# def send_overdue_fee_reminders():
#     """
#     Manually triggered task to send reminders for overdue fees.
#
#     This should be called via a cron job or scheduled task.
#     """
#     from finance.models import DebtRecord
#     from academic.models import Parent
#
#     # Find all debts with remaining balance
#     overdue_debts = DebtRecord.objects.filter(
#         remaining_balance__gt=0
#     ).select_related('student', 'student__parent_guardian', 'student__parent_guardian__user')
#
#     sent_count = 0
#     error_count = 0
#
#     for debt in overdue_debts:
#         student = debt.student
#         if not student.parent_guardian:
#             continue
#
#         parent_user = student.parent_guardian.user
#
#         try:
#             notification_service.create_notification(
#                 recipient=parent_user,
#                 notification_type='fee',
#                 title=f"Fee Payment Reminder: {student.full_name}",
#                 message=f"This is a reminder that {student.full_name} has an outstanding fee balance of "
#                         f"₦{debt.remaining_balance:,.2f} for {debt.term}. "
#                         f"Please arrange payment at your earliest convenience.",
#                 priority='high',
#                 related_student=student,
#                 related_object=debt,
#                 send_email=True,
#                 send_sms=True  # SMS for overdue reminders
#             )
#             sent_count += 1
#         except Exception as e:
#             logger.error(f"Failed to send overdue reminder for debt {debt.id}: {str(e)}")
#             error_count += 1
#
#     logger.info(f"Overdue fee reminders sent: {sent_count} successful, {error_count} errors")
#     return {'sent': sent_count, 'errors': error_count}


# Helper function to send exam reminders
def send_upcoming_exam_reminders(days_ahead=7):
    """
    Send reminders for upcoming exams.

    Args:
        days_ahead: Number of days in advance to send reminders

    This should be called via a cron job or scheduled task.
    """
    from examination.models import Exam
    from academic.models import Parent
    from users.models import CustomUser

    # Find exams happening in the next X days
    today = timezone.now().date()
    upcoming_date = today + timedelta(days=days_ahead)

    upcoming_exams = Exam.objects.filter(
        date__gte=today,
        date__lte=upcoming_date
    ).select_related('subject', 'classroom')

    sent_count = 0
    error_count = 0

    for exam in upcoming_exams:
        # Get all students in the exam's classroom
        students = exam.classroom.students.filter(is_active=True)

        for student in students:
            if not student.parent_guardian:
                continue

            parent_user = student.parent_guardian.user
            days_until = (exam.date - today).days

            try:
                notification_service.create_notification(
                    recipient=parent_user,
                    notification_type='exam',
                    title=f"Upcoming Exam: {exam.subject.name}",
                    message=f"{student.full_name} has an upcoming {exam.subject.name} exam "
                            f"on {exam.date.strftime('%B %d, %Y')} ({days_until} days away). "
                            f"Please ensure your child is prepared.",
                    priority='normal',
                    related_student=student,
                    related_object=exam,
                    send_email=True,
                    send_sms=False
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send exam reminder for student {student.id}: {str(e)}")
                error_count += 1

    logger.info(f"Exam reminders sent: {sent_count} successful, {error_count} errors")
    return {'sent': sent_count, 'errors': error_count}
