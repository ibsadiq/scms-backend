"""
Assignment Signals - Phase 1.7: Assignment & Homework Management

Automatically trigger notifications for:
- New assignments posted
- Assignment due date reminders
- Submission received
- Assignment graded
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta

from .models import Assignment, AssignmentSubmission, AssignmentGrade
from notifications.services import NotificationService

logger = logging.getLogger(__name__)
notification_service = NotificationService()


@receiver(post_save, sender=Assignment)
def notify_new_assignment(sender, instance, created, **kwargs):
    """
    Send notification when teacher creates/publishes a new assignment.
    
    Notifies:
    - Students in the classroom (if they have accounts)
    - Parents of all students in the classroom
    """
    if not created:
        # Only send on status change to published
        if instance.status != 'published':
            return
        
        # Check if this is a status change (not initial creation)
        try:
            old_instance = Assignment.objects.get(pk=instance.pk)
            if old_instance.status == 'published':
                return  # Already notified
        except Assignment.DoesNotExist:
            pass
    
    if instance.status != 'published':
        return  # Only notify for published assignments
    
    # Get all students in the classroom
    students = instance.classroom.students.filter(is_active=True)
    
    for student in students:
        # Notify student if they have an account
        if student.user and student.can_login:
            try:
                notification_service.create_notification(
                    recipient=student.user,
                    notification_type='assignment',
                    title=f"New Assignment: {instance.title}",
                    message=f"Your teacher has assigned {instance.title} for {instance.subject.name}. "
                            f"Due: {instance.due_date.strftime('%B %d, %Y at %I:%M %p')}. "
                            f"Type: {instance.get_assignment_type_display()}",
                    priority='normal',
                    related_student=student,
                    related_object=instance,
                    send_email=True,
                    send_sms=False
                )
                logger.info(f"Assignment notification sent to student {student.id}")
            except Exception as e:
                logger.error(f"Failed to send assignment notification to student {student.id}: {str(e)}")
        
        # Notify parent
        if student.parent_guardian and student.parent_guardian.user:
            try:
                notification_service.create_notification(
                    recipient=student.parent_guardian.user,
                    notification_type='assignment',
                    title=f"New Assignment for {student.full_name}",
                    message=f"{student.full_name} has a new assignment: {instance.title} ({instance.subject.name}). "
                            f"Due: {instance.due_date.strftime('%B %d, %Y')}. "
                            f"Type: {instance.get_assignment_type_display()}",
                    priority='normal',
                    related_student=student,
                    related_object=instance,
                    send_email=True,
                    send_sms=False
                )
                logger.info(f"Assignment notification sent to parent of student {student.id}")
            except Exception as e:
                logger.error(f"Failed to send assignment notification to parent: {str(e)}")


@receiver(post_save, sender=AssignmentSubmission)
def notify_submission_received(sender, instance, created, **kwargs):
    """
    Send notification when student submits an assignment.
    
    Notifies:
    - Teacher who created the assignment
    - Parent of the student (confirmation of submission)
    """
    if not created:
        return  # Only on new submissions
    
    student = instance.student
    assignment = instance.assignment
    teacher = assignment.teacher
    
    # Notify teacher
    if teacher.user:
        try:
            late_text = " (LATE)" if instance.is_late else ""
            notification_service.create_notification(
                recipient=teacher.user,
                notification_type='assignment',
                title=f"Submission Received{late_text}: {assignment.title}",
                message=f"{student.full_name} has submitted their assignment for '{assignment.title}'{late_text}. "
                        f"Classroom: {assignment.classroom}",
                priority='low',
                related_student=student,
                related_object=instance,
                send_email=True,
                send_sms=False
            )
            logger.info(f"Submission notification sent to teacher {teacher.id}")
        except Exception as e:
            logger.error(f"Failed to send submission notification to teacher: {str(e)}")
    
    # Notify parent (confirmation)
    if student.parent_guardian and student.parent_guardian.user:
        try:
            late_text = " after the due date" if instance.is_late else ""
            notification_service.create_notification(
                recipient=student.parent_guardian.user,
                notification_type='assignment',
                title=f"Assignment Submitted: {assignment.title}",
                message=f"{student.full_name} has submitted their assignment '{assignment.title}' for {assignment.subject.name}{late_text}.",
                priority='low',
                related_student=student,
                related_object=instance,
                send_email=True,
                send_sms=False
            )
            logger.info(f"Submission confirmation sent to parent of student {student.id}")
        except Exception as e:
            logger.error(f"Failed to send submission confirmation to parent: {str(e)}")


@receiver(post_save, sender=AssignmentGrade)
def notify_assignment_graded(sender, instance, created, **kwargs):
    """
    Send notification when assignment is graded.
    
    Notifies:
    - Student (if they have an account)
    - Parent of the student
    """
    if not created:
        return  # Only on new grades
    
    submission = instance.submission
    student = submission.student
    assignment = submission.assignment
    
    # Notify student if they have account
    if student.user and student.can_login:
        try:
            notification_service.create_notification(
                recipient=student.user,
                notification_type='assignment',
                title=f"Assignment Graded: {assignment.title}",
                message=f"Your assignment '{assignment.title}' has been graded. "
                        f"Score: {instance.final_score}/{assignment.max_score} ({instance.percentage}% - Grade {instance.grade_letter}). "
                        f"{f'Feedback: {instance.feedback[:100]}...' if instance.feedback else 'No feedback provided.'}",
                priority='normal',
                related_student=student,
                related_object=instance,
                send_email=True,
                send_sms=False
            )
            logger.info(f"Grade notification sent to student {student.id}")
        except Exception as e:
            logger.error(f"Failed to send grade notification to student: {str(e)}")
    
    # Notify parent
    if student.parent_guardian and student.parent_guardian.user:
        try:
            notification_service.create_notification(
                recipient=student.parent_guardian.user,
                notification_type='assignment',
                title=f"Assignment Graded: {student.full_name}",
                message=f"{student.full_name}'s assignment '{assignment.title}' ({assignment.subject.name}) has been graded. "
                        f"Score: {instance.final_score}/{assignment.max_score} ({instance.percentage}% - Grade {instance.grade_letter})",
                priority='normal',
                related_student=student,
                related_object=instance,
                send_email=True,
                send_sms=False
            )
            logger.info(f"Grade notification sent to parent of student {student.id}")
        except Exception as e:
            logger.error(f"Failed to send grade notification to parent: {str(e)}")


# Helper function for scheduled reminders (cron job/celery task)
def send_assignment_due_reminders(days_ahead=1):
    """
    Send reminders for assignments due within X days.
    
    Args:
        days_ahead: Number of days ahead to check (default: 1 = tomorrow)
    
    This should be called via a cron job or scheduled task.
    """
    from django.db.models import Q
    
    today = timezone.now()
    target_date = today + timedelta(days=days_ahead)
    
    # Find published assignments due within the timeframe
    upcoming_assignments = Assignment.objects.filter(
        status='published',
        is_active=True,
        due_date__gte=today,
        due_date__lte=target_date
    ).select_related('classroom', 'subject', 'teacher')
    
    sent_count = 0
    error_count = 0
    
    for assignment in upcoming_assignments:
        # Get students who haven't submitted yet
        submitted_student_ids = assignment.submissions.values_list('student_id', flat=True)
        pending_students = assignment.classroom.students.filter(
            is_active=True
        ).exclude(id__in=submitted_student_ids)
        
        days_remaining = (assignment.due_date - today).days
        hours_remaining = int((assignment.due_date - today).total_seconds() / 3600)
        
        priority = 'high' if days_remaining <= 1 else 'normal'
        
        for student in pending_students:
            # Notify student if they have account
            if student.user and student.can_login:
                try:
                    if hours_remaining < 24:
                        time_text = f"{hours_remaining} hours"
                    else:
                        time_text = f"{days_remaining} days"
                    
                    notification_service.create_notification(
                        recipient=student.user,
                        notification_type='assignment',
                        title=f"Assignment Due Soon: {assignment.title}",
                        message=f"Reminder: '{assignment.title}' for {assignment.subject.name} is due in {time_text} "
                                f"({assignment.due_date.strftime('%B %d at %I:%M %p')}). "
                                f"Don't forget to submit!",
                        priority=priority,
                        related_student=student,
                        related_object=assignment,
                        send_email=True,
                        send_sms=priority == 'high'  # SMS for urgent (< 24 hours)
                    )
                    sent_count += 1
                except Exception as e:
                    logger.error(f"Failed to send reminder to student {student.id}: {str(e)}")
                    error_count += 1
            
            # Notify parent
            if student.parent_guardian and student.parent_guardian.user:
                try:
                    notification_service.create_notification(
                        recipient=student.parent_guardian.user,
                        notification_type='assignment',
                        title=f"Assignment Due Soon: {student.full_name}",
                        message=f"Reminder: {student.full_name} has not yet submitted '{assignment.title}' "
                                f"which is due in {days_remaining} days ({assignment.due_date.strftime('%B %d')}).",
                        priority=priority,
                        related_student=student,
                        related_object=assignment,
                        send_email=True,
                        send_sms=False
                    )
                    sent_count += 1
                except Exception as e:
                    logger.error(f"Failed to send reminder to parent: {str(e)}")
                    error_count += 1
    
    logger.info(f"Assignment due reminders sent: {sent_count} successful, {error_count} errors")
    return {'sent': sent_count, 'errors': error_count}
