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
                ).select_related('student', 'student__parent_guardian', 'student__parent_guardian__user', 'fee_structure')
                
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

                    parent = assignment.student.parent_guardian
                    if parent:
                        parent_user = getattr(parent, 'user', None) or (
                            CustomUser.objects.filter(email=parent.email, is_parent=True).first()
                            if getattr(parent, 'email', None) else None
                        )

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
            ).select_related('student', 'student__parent_guardian', 'student__parent_guardian__user')

            for assignment in assignments:
                balance = assignment.amount_owed - assignment.amount_paid

                parent = assignment.student.parent_guardian
                if parent:
                    parent_user = getattr(parent, 'user', None) or (
                        CustomUser.objects.filter(email=parent.email, is_parent=True).first()
                        if getattr(parent, 'email', None) else None
                    )

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


def _to_base64_uri(field_or_url):
    if not field_or_url:
        return None
    import base64, mimetypes, os, requests
    try:
        if hasattr(field_or_url, 'open'):
            f = field_or_url.open('rb')
            data = f.read()
            mime, _ = mimetypes.guess_type(getattr(field_or_url, 'name', 'file.jpg'))
            mime = mime or 'image/jpeg'
            encoded = base64.b64encode(data).decode('utf-8')
            return f"data:{mime};base64,{encoded}"
    except Exception:
        pass

    if isinstance(field_or_url, str) and (field_or_url.startswith('http://') or field_or_url.startswith('https://')):
        try:
            res = requests.get(field_or_url, timeout=5)
            if res.status_code == 200:
                mime = res.headers.get('Content-Type', 'image/jpeg')
                encoded = base64.b64encode(res.content).decode('utf-8')
                return f"data:{mime};base64,{encoded}"
        except Exception:
            pass
    elif isinstance(field_or_url, str) and os.path.exists(field_or_url):
        try:
            with open(field_or_url, 'rb') as f:
                data = f.read()
                mime, _ = mimetypes.guess_type(field_or_url)
                mime = mime or 'image/jpeg'
                encoded = base64.b64encode(data).decode('utf-8')
                return f"data:{mime};base64,{encoded}"
        except Exception:
            pass
    return field_or_url


def render_receipt_pdf(receipt):
    """
    Render PDF receipt using WeasyPrint with school logo and tenant info.
    """
    from weasyprint import HTML
    from django.utils import timezone as tz
    from tenants.models import Client
    from django.db import connection

    schema_name = connection.schema_name
    try:
        client_tenant = Client.objects.get(schema_name=schema_name)
    except Exception:
        client_tenant = None

    logo_uri = None
    if client_tenant and getattr(client_tenant, 'logo', None) and client_tenant.logo:
        logo_uri = _to_base64_uri(client_tenant.logo)

    school_info = {
        'name': getattr(client_tenant, 'name', 'SCHOOL NAME') if client_tenant else 'SCHOOL NAME',
        'address': getattr(client_tenant, 'address', '') or '' if client_tenant else '',
        'phone': getattr(client_tenant, 'contact_phone', '') or '' if client_tenant else '',
        'email': getattr(client_tenant, 'contact_email', '') or '' if client_tenant else '',
        'logo': logo_uri,
        'motto': getattr(client_tenant, 'motto', '') or '' if client_tenant else '',
    }

    allocations = receipt.fee_allocations.select_related(
        'fee_assignment__fee_structure'
    ).all()

    student = receipt.student
    if student:
        raw_name = getattr(student, 'full_name', None) or f"{student.first_name} {student.last_name}"
        student_name = raw_name.strip().title()
    else:
        student_name = (receipt.payer or '—').strip().title()

    admission_no = student.admission_number if student else "—"
    classroom = str(student.classroom.name) if student and student.classroom else "—"

    fee_rows = ""
    for alloc in allocations:
        fee_name = alloc.fee_assignment.fee_structure.name if alloc.fee_assignment else "Fee"
        fee_rows += f"""
        <tr>
            <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;">{fee_name}</td>
            <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;text-align:right;">
                &#8358;{alloc.amount:,.2f}
            </td>
        </tr>"""

    if not fee_rows:
        fee_rows = f"""
        <tr>
            <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;">School Fees</td>
            <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;text-align:right;">
                &#8358;{receipt.amount:,.2f}
            </td>
        </tr>"""

    term_name = str(receipt.term.name) if (receipt.term and hasattr(receipt.term, 'name')) else (str(receipt.term) if receipt.term else "—")
    payment_date = receipt.payment_date.strftime("%d %B %Y") if receipt.payment_date else "—"
    generated_at = tz.now().strftime("%d %B %Y, %H:%M")

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8"/>
      <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family: Inter, Arial, sans-serif; background:#ffffff; color:#111827; font-size:13px; }}
        .page {{ max-width:680px; margin:20px auto; background:#fff; border-radius:12px;
                 border:1px solid #e5e7eb; padding:36px; }}
        .header {{ display:flex; justify-content:space-between; align-items:center;
                   border-bottom:2px solid #059669; padding-bottom:20px; margin-bottom:24px; }}
        .brand {{ display:flex; align-items:center; gap:28px; }}
        .logo {{ max-height:65px; max-width:140px; object-fit:contain; margin-right:24px; }}
        .school-name {{ font-size:16px; font-weight:700; color:#059669; line-height:1.2; }}
        .school-info {{ font-size:11px; color:#4b5563; margin-top:3px; }}
        .school-motto {{ font-size:11px; font-style:italic; color:#059669; margin-top:2px; }}
        .receipt-badge {{ background:#059669; color:#fff; padding:6px 18px;
                          border-radius:20px; font-size:12px; font-weight:600; letter-spacing:0.05em; }}
        .receipt-no {{ font-size:22px; font-weight:700; color:#111827; text-align:right; margin-top:6px; }}
        .receipt-subtitle-row {{ text-align:center; margin-top:16px; margin-bottom:22px; border-bottom:1px solid #e5e7eb; padding-bottom:10px; }}
        .receipt-subtitle {{ font-size:13px; font-weight:700; color:#059669; letter-spacing:0.06em; text-transform:uppercase; }}
        .section-label {{ font-size:10px; font-weight:700; color:#6b7280;
                           text-transform:uppercase; letter-spacing:.05em; margin-bottom:4px; }}
        .info-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:24px; }}
        .info-block p {{ font-size:14px; font-weight:600; color:#111827; }}
        table {{ width:100%; border-collapse:collapse; margin-bottom:20px; margin-top:10px; }}
        thead th {{ background:#f3f4f6; padding:10px 12px; text-align:left; font-size:11px;
                    font-weight:700; color:#374151; text-transform:uppercase; letter-spacing:.04em; }}
        thead th:last-child {{ text-align:right; }}
        .total-row td {{ padding:12px; font-weight:700; font-size:15px;
                         background:#f0fdf4; color:#065f46; border-top:2px solid #059669; }}
        .total-row td:last-child {{ text-align:right; }}
        .status-badge {{ display:inline-block; background:#d1fae5; color:#065f46;
                          border-radius:12px; padding:3px 12px; font-size:12px; font-weight:600; }}
        .footer {{ margin-top:28px; padding-top:18px; border-top:1px solid #e5e7eb;
                   text-align:center; font-size:11px; color:#9ca3af; }}
      </style>
    </head>
    <body>
      <div class="page">
        <div class="header">
          <div class="brand">
            {"<img class='logo' src='" + logo_uri + "' />" if logo_uri else ""}
            <div>
              <div class="school-name">{school_info['name']}</div>
              {"<div class='school-info'>" + school_info['address'] + "</div>" if school_info['address'] else ""}
              {"<div class='school-info'>Tel: " + school_info['phone'] + " | Email: " + school_info['email'] + "</div>" if (school_info['phone'] or school_info['email']) else ""}
              {"<div class='school-motto'>\"" + school_info['motto'] + "\"</div>" if school_info['motto'] else ""}
            </div>
          </div>
          <div style="text-align:right;">
            <span class="receipt-badge">RECEIPT</span>
            <div class="receipt-no">#{receipt.receipt_number}</div>
          </div>
        </div>

        <div class="receipt-subtitle-row">
          <span class="receipt-subtitle">Official Payment Receipt</span>
        </div>

        <div class="info-grid">
          <div class="info-block">
            <div class="section-label">Student</div>
            <p>{student_name}</p>
            <div style="color:#6b7280;font-size:12px;margin-top:2px;">
              Adm No: {admission_no} &nbsp;|&nbsp; Class: {classroom}
            </div>
          </div>
          <div class="info-block">
            <div class="section-label">Payment Details</div>
            <p>{payment_date}</p>
            <div style="color:#6b7280;font-size:12px;margin-top:2px;">
              Method: {receipt.paid_through} &nbsp;|&nbsp; Term: {term_name}
            </div>
          </div>
          <div class="info-block">
            <div class="section-label">Payer</div>
            <p>{(receipt.payer or '—').strip().title()}</p>
          </div>
          <div class="info-block">
            <div class="section-label">Status</div>
            <span class="status-badge">{receipt.status}</span>
          </div>
        </div>

        <table>
          <thead>
            <tr>
              <th>Description</th>
              <th style="text-align:right;">Amount</th>
            </tr>
          </thead>
          <tbody>
            {fee_rows}
          </tbody>
          <tfoot>
            <tr class="total-row">
              <td>Total Paid</td>
              <td>&#8358;{receipt.amount:,.2f}</td>
            </tr>
          </tfoot>
        </table>

        {"<p style='font-size:12px;color:#6b7280;margin-bottom:12px;'><strong>Remarks:</strong> " + receipt.remarks + "</p>" if receipt.remarks else ""}
        {"<p style='font-size:12px;color:#6b7280;'><strong>Reference:</strong> " + receipt.reference_number + "</p>" if receipt.reference_number else ""}

        <div class="footer">
          <p>This is a computer-generated receipt. No signature required.</p>
          <p style="margin-top:4px;">Generated on {generated_at} &nbsp;|&nbsp; {school_info['name']} Finance</p>
        </div>
      </div>
    </body>
    </html>
    """

    return HTML(string=html_content).write_pdf()


@shared_task(bind=True, name='finance.generate_receipt_pdf')
def generate_receipt_pdf_task(self, schema_name, receipt_id):
    """
    Celery task to generate receipt PDF in tenant context.
    """
    from finance.models import Receipt
    with schema_context(schema_name):
        receipt = Receipt.objects.select_related('student', 'student__classroom', 'term').get(id=receipt_id)
        pdf_bytes = render_receipt_pdf(receipt)
        return {
            'status': 'success',
            'receipt_number': receipt.receipt_number,
            'pdf_size': len(pdf_bytes)
        }

