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
from tenants.models import Client
from django_tenants.utils import schema_context


@shared_task(name='finance.send_fee_reminders')
def send_fee_reminders():
    """
    Send fee payment reminders to parents based on configurable ReminderSettings.
    """
    today = timezone.now().date()
    notification_service = NotificationService()

    results = {
        'sent': 0,
        'errors': []
    }

    active_tenants = Client.objects.exclude(schema_name='public')
    for tenant in active_tenants:
        with schema_context(tenant.schema_name):
            from finance.models import ReminderSetting
            active_rules = ReminderSetting.objects.filter(is_active=True)

            for rule in active_rules:
                target_date = today + timedelta(days=rule.days_before_due)
                
                # Get assignments where due date is target_date and balance > 0
                assignments = StudentFeeAssignment.objects.filter(
                    fee_structure__due_date=target_date,
                    amount_paid__lt=F('amount_owed'),
                    is_waived=False
                ).select_related('student', 'student__parent', 'fee_structure')
                
                # If the rule has a fee_structure, ONLY process assignments for that fee.
                if rule.fee_structure:
                    assignments = assignments.filter(fee_structure=rule.fee_structure)
                else:
                    # If it has NO fee_structure, process all fees EXCEPT those that have their own specific rules for the same days_before_due
                    specific_fee_ids = ReminderSetting.objects.filter(
                        is_active=True, 
                        days_before_due=rule.days_before_due, 
                        fee_structure__isnull=False
                    ).values_list('fee_structure_id', flat=True)
                    assignments = assignments.exclude(fee_structure_id__in=specific_fee_ids)

                for assignment in assignments:
                    balance = assignment.amount_owed - assignment.amount_paid
                    if balance <= 0:
                        continue

                    # Determine template
                    template = rule.message_template
                    if assignment.amount_paid > 0 and rule.partial_payment_template:
                        template = rule.partial_payment_template

                    # Replace variables safely
                    message = template.replace('{{student_name}}', assignment.student.full_name)
                    message = message.replace('{{fee_name}}', assignment.fee_structure.name)
                    message = message.replace('{{amount_owed}}', f"₦{assignment.amount_owed:,.2f}")
                    message = message.replace('{{balance}}', f"₦{balance:,.2f}")
                    message = message.replace('{{amount_paid}}', f"₦{assignment.amount_paid:,.2f}")
                    if assignment.fee_structure.due_date:
                        message = message.replace('{{due_date}}', assignment.fee_structure.due_date.strftime("%B %d, %Y"))
                    else:
                        message = message.replace('{{due_date}}', 'N/A')

                    if assignment.student.parent:
                        parent_user = CustomUser.objects.filter(
                            email=assignment.student.parent.email,
                            is_parent=True
                        ).first()

                        if parent_user:
                            try:
                                title = 'Fee Payment Reminder'
                                if rule.days_before_due <= 3 and rule.days_before_due >= 0:
                                    title = 'Urgent: Fee Payment Due Soon'
                                elif rule.days_before_due < 0:
                                    title = 'Overdue Payment'
                                    
                                # Default priorities based on days before due
                                priority = 'normal'
                                send_sms = False
                                if rule.days_before_due <= 3 and rule.days_before_due > 0:
                                    priority = 'high'
                                    send_sms = True
                                elif rule.days_before_due <= 0:
                                    priority = 'urgent'
                                    send_sms = True

                                notification_service.create_notification(
                                    recipient=parent_user,
                                    notification_type='fee',
                                    title=title,
                                    message=message,
                                    priority=priority,
                                    send_email=True,
                                    send_sms=send_sms,
                                    related_student=assignment.student
                                )
                                results['sent'] += 1
                            except Exception as e:
                                results['errors'].append(f"[{tenant.schema_name}] Rule {rule.name} - Student {assignment.student.id}: {str(e)}")

    return results


@shared_task(name='finance.send_custom_fee_reminder')
def send_custom_fee_reminder(schema_name, fee_structure_id, message=None):
    """
    Send a custom reminder for a specific fee structure.

    Args:
        schema_name: The tenant schema to execute in
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

    with schema_context(schema_name):
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
def bulk_assign_fees_task(self, schema_name, fee_structure_id, term_id=None):
    """
    Async task for bulk assigning fees to students.

    Args:
        self: Celery task instance
        schema_name: The tenant schema to execute in
        fee_structure_id: ID of fee structure to assign
        term_id: Optional term ID

    Returns:
        dict: Assignment summary
    """
    from finance.models import FeeStructure
    from administration.models import Term

    with schema_context(schema_name):
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
