"""
Celery tasks for finance operations.

Handles asynchronous operations like:
- Fee reminder notifications
- Overdue payment alerts
- Bulk fee assignments
"""
from celery import shared_task
from django.utils import timezone
from django.db.models import Q, Sum, F
from datetime import timedelta

from finance.models import FeeStructure, StudentFeeAssignment
from notifications.services import NotificationService
from users.models import CustomUser


@shared_task(name='finance.send_fee_reminders')
def send_fee_reminders():
    """
    Send fee payment reminders to parents.

    Runs daily to check for:
    - Fees due in 7 days (first reminder)
    - Fees due in 3 days (second reminder)
    - Fees due in 1 day (final reminder)
    - Overdue fees

    Returns:
        dict: Summary of reminders sent
    """
    today = timezone.now().date()
    notification_service = NotificationService()

    results = {
        'week_ahead': 0,
        'three_days': 0,
        'tomorrow': 0,
        'overdue': 0,
        'errors': []
    }

    # 1. Send reminders for fees due in 7 days
    week_ahead_date = today + timedelta(days=7)
    week_ahead_fees = FeeStructure.objects.filter(
        due_date=week_ahead_date
    ).select_related('academic_year', 'term')

    for fee_structure in week_ahead_fees:
        # Get unpaid assignments for this fee
        assignments = StudentFeeAssignment.objects.filter(
            fee_structure=fee_structure,
            amount_paid__lt=F('amount_owed'),  # Not fully paid
            is_waived=False
        ).select_related('student', 'student__parent')

        for assignment in assignments:
            balance = assignment.amount_owed - assignment.amount_paid

            # Send to parent
            if assignment.student.parent:
                parent_user = CustomUser.objects.filter(
                    email=assignment.student.parent.email,
                    is_parent=True
                ).first()

                if parent_user:
                    try:
                        notification_service.create_notification(
                            recipient=parent_user,
                            notification_type='fee',
                            title='Fee Payment Reminder',
                            message=f'Reminder: {fee_structure.name} (₦{balance:,.2f}) is due in 7 days on {fee_structure.due_date.strftime("%B %d, %Y")}. Student: {assignment.student.full_name}',
                            priority='normal',
                            send_email=True,
                            send_sms=False,
                            related_student=assignment.student
                        )
                        results['week_ahead'] += 1
                    except Exception as e:
                        results['errors'].append(f"Week ahead - Student {assignment.student.id}: {str(e)}")

    # 2. Send reminders for fees due in 3 days
    three_days_ahead = today + timedelta(days=3)
    three_day_fees = FeeStructure.objects.filter(
        due_date=three_days_ahead
    ).select_related('academic_year', 'term')

    for fee_structure in three_day_fees:
        assignments = StudentFeeAssignment.objects.filter(
            fee_structure=fee_structure,
            amount_paid__lt=F('amount_owed'),
            is_waived=False
        ).select_related('student', 'student__parent')

        for assignment in assignments:
            balance = assignment.amount_owed - assignment.amount_paid

            if assignment.student.parent:
                parent_user = CustomUser.objects.filter(
                    email=assignment.student.parent.email,
                    is_parent=True
                ).first()

                if parent_user:
                    try:
                        notification_service.create_notification(
                            recipient=parent_user,
                            notification_type='fee',
                            title='Urgent: Fee Payment Due Soon',
                            message=f'Urgent: {fee_structure.name} (₦{balance:,.2f}) is due in 3 days on {fee_structure.due_date.strftime("%B %d, %Y")}. Please make payment soon. Student: {assignment.student.full_name}',
                            priority='high',
                            send_email=True,
                            send_sms=True,  # Enable SMS for urgent reminders
                            related_student=assignment.student
                        )
                        results['three_days'] += 1
                    except Exception as e:
                        results['errors'].append(f"3 days - Student {assignment.student.id}: {str(e)}")

    # 3. Send reminders for fees due tomorrow
    tomorrow = today + timedelta(days=1)
    tomorrow_fees = FeeStructure.objects.filter(
        due_date=tomorrow
    ).select_related('academic_year', 'term')

    for fee_structure in tomorrow_fees:
        assignments = StudentFeeAssignment.objects.filter(
            fee_structure=fee_structure,
            amount_paid__lt=F('amount_owed'),
            is_waived=False
        ).select_related('student', 'student__parent')

        for assignment in assignments:
            balance = assignment.amount_owed - assignment.amount_paid

            if assignment.student.parent:
                parent_user = CustomUser.objects.filter(
                    email=assignment.student.parent.email,
                    is_parent=True
                ).first()

                if parent_user:
                    try:
                        notification_service.create_notification(
                            recipient=parent_user,
                            notification_type='fee',
                            title='Final Reminder: Fee Due Tomorrow',
                            message=f'Final reminder: {fee_structure.name} (₦{balance:,.2f}) is due tomorrow on {fee_structure.due_date.strftime("%B %d, %Y")}. Please pay immediately. Student: {assignment.student.full_name}',
                            priority='urgent',
                            send_email=True,
                            send_sms=True,
                            related_student=assignment.student
                        )
                        results['tomorrow'] += 1
                    except Exception as e:
                        results['errors'].append(f"Tomorrow - Student {assignment.student.id}: {str(e)}")

    # 4. Send overdue payment alerts
    overdue_fees = FeeStructure.objects.filter(
        due_date__lt=today
    ).select_related('academic_year', 'term')

    for fee_structure in overdue_fees:
        # Only send overdue notices once a week
        days_overdue = (today - fee_structure.due_date).days

        # Send on days 1, 7, 14, 21, 28, etc (weekly after first day)
        if days_overdue == 1 or (days_overdue > 7 and days_overdue % 7 == 0):
            assignments = StudentFeeAssignment.objects.filter(
                fee_structure=fee_structure,
                amount_paid__lt=F('amount_owed'),
                is_waived=False
            ).select_related('student', 'student__parent')

            for assignment in assignments:
                balance = assignment.amount_owed - assignment.amount_paid

                if assignment.student.parent:
                    parent_user = CustomUser.objects.filter(
                        email=assignment.student.parent.email,
                        is_parent=True
                    ).first()

                    if parent_user:
                        try:
                            notification_service.create_notification(
                                recipient=parent_user,
                                notification_type='fee',
                                title=f'Overdue Payment: {days_overdue} Day(s)',
                                message=f'Payment overdue: {fee_structure.name} (₦{balance:,.2f}) was due on {fee_structure.due_date.strftime("%B %d, %Y")} ({days_overdue} days ago). Please pay immediately to avoid penalties. Student: {assignment.student.full_name}',
                                priority='urgent',
                                send_email=True,
                                send_sms=True,
                                related_student=assignment.student
                            )
                            results['overdue'] += 1
                        except Exception as e:
                            results['errors'].append(f"Overdue - Student {assignment.student.id}: {str(e)}")

    return results


@shared_task(name='finance.send_custom_fee_reminder')
def send_custom_fee_reminder(fee_structure_id, message=None):
    """
    Send a custom reminder for a specific fee structure.

    Args:
        fee_structure_id: ID of the fee structure
        message: Optional custom message (uses default if None)

    Returns:
        dict: Summary of reminders sent
    """
    from finance.models import FeeStructure

    notification_service = NotificationService()
    results = {
        'sent': 0,
        'errors': []
    }

    try:
        fee_structure = FeeStructure.objects.get(id=fee_structure_id)

        # Get all unpaid assignments
        assignments = StudentFeeAssignment.objects.filter(
            fee_structure=fee_structure,
            amount_paid__lt=F('amount_owed'),
            is_waived=False
        ).select_related('student', 'student__parent')

        for assignment in assignments:
            balance = assignment.amount_owed - assignment.amount_paid

            if assignment.student.parent:
                parent_user = CustomUser.objects.filter(
                    email=assignment.student.parent.email,
                    is_parent=True
                ).first()

                if parent_user:
                    try:
                        default_message = f'{fee_structure.name} payment of ₦{balance:,.2f} is pending. '
                        if fee_structure.due_date:
                            default_message += f'Due date: {fee_structure.due_date.strftime("%B %d, %Y")}. '
                        default_message += f'Student: {assignment.student.full_name}'

                        notification_service.create_notification(
                            recipient=parent_user,
                            notification_type='fee',
                            title=f'Fee Payment Reminder',
                            message=message or default_message,
                            priority='normal',
                            send_email=True,
                            send_sms=False,
                            related_student=assignment.student
                        )
                        results['sent'] += 1
                    except Exception as e:
                        results['errors'].append(f"Student {assignment.student.id}: {str(e)}")

        return results

    except FeeStructure.DoesNotExist:
        results['errors'].append(f"FeeStructure {fee_structure_id} not found")
        return results


@shared_task(bind=True, name='finance.bulk_assign_fees')
def bulk_assign_fees_task(self, fee_structure_id, term_id=None):
    """
    Async task for bulk assigning fees to students.

    Args:
        self: Celery task instance
        fee_structure_id: ID of fee structure to assign
        term_id: Optional term ID

    Returns:
        dict: Assignment summary
    """
    from finance.models import FeeStructure
    from administration.models import Term

    try:
        fee_structure = FeeStructure.objects.get(id=fee_structure_id)

        term = None
        if term_id:
            term = Term.objects.get(id=term_id)

        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={'status': f'Assigning {fee_structure.name} to students...'}
        )

        # Use the model's auto_assign method
        assigned_count = fee_structure.auto_assign_to_students(term=term)

        return {
            'status': 'success',
            'fee_structure': fee_structure.name,
            'assigned_count': assigned_count
        }

    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e)
        }
