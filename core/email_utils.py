"""
Email utility functions for sending various types of emails.
"""
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags


def get_school_settings():
    """
    Get school settings from database.
    Falls back to settings if not found.
    """
    try:
        from tenants.models import SchoolSettings
        school_settings = SchoolSettings.get_settings()

        # Get logo URL (full URL for emails)
        logo_url = None
        if school_settings.logo:
            # Use FRONTEND_URL for public-facing URLs (goes through nginx)
            # If FRONTEND_URL is not set, fall back to BASE_URL
            base_url = getattr(settings, 'FRONTEND_URL', None) or getattr(settings, 'BASE_URL', 'http://localhost:8000')
            # Remove any trailing slashes from base_url
            base_url = base_url.rstrip('/')
            logo_url = f"{base_url}{school_settings.logo.url}"

        return {
            'school_name': school_settings.school_name,
            'contact_email': school_settings.contact_email,
            'contact_phone': school_settings.contact_phone,
            'website': school_settings.website,
            'address': school_settings.address,
            'primary_color': school_settings.primary_color,
            'logo_url': logo_url,
        }
    except Exception:
        # Fallback to settings if database not available or model doesn't exist
        return {
            'school_name': getattr(settings, 'SCHOOL_NAME', 'SureStart Schools'),
            'contact_email': None,
            'contact_phone': None,
            'website': None,
            'address': None,
            'primary_color': '#047857',
            'logo_url': None,
        }


def send_email(
    subject,
    to_email,
    template_name,
    context,
    from_email=None,
    fail_silently=False
):
    """
    Send an HTML email using Django templates.

    Args:
        subject: Email subject line
        to_email: Recipient email address (string) or list of addresses
        template_name: Name of the template (without path or extension)
                      Templates should be in core/templates/email/
        context: Dictionary of context variables for the template
        from_email: Sender email (defaults to DEFAULT_FROM_EMAIL)
        fail_silently: If True, don't raise exceptions on failure

    Returns:
        Number of successfully sent emails (0 or 1)
    """
    # Ensure to_email is a list
    if isinstance(to_email, str):
        to_email = [to_email]

    # Set default from_email
    if from_email is None:
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@hayatul.com')

    # Get school settings from database
    school_settings = get_school_settings()

    # Add default context variables
    context.setdefault('app_name', getattr(settings, 'APP_NAME', 'School Management System'))
    context.setdefault('school_name', school_settings['school_name'])
    context.setdefault('school_contact_email', school_settings['contact_email'])
    context.setdefault('school_contact_phone', school_settings['contact_phone'])
    context.setdefault('school_website', school_settings['website'])
    context.setdefault('school_address', school_settings['address'])
    context.setdefault('school_logo_url', school_settings['logo_url'])
    context.setdefault('school_primary_color', school_settings['primary_color'])
    context.setdefault('base_url', getattr(settings, 'BASE_URL', 'http://localhost:3000'))

    # Render HTML template
    html_content = render_to_string(f'email/{template_name}.html', context)

    # Try to render text template, fall back to stripping HTML
    try:
        text_content = render_to_string(f'email/{template_name}.txt', context)
    except:
        text_content = strip_tags(html_content)

    # Create email message
    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=from_email,
        to=to_email
    )
    email.attach_alternative(html_content, "text/html")

    # Send email
    try:
        return email.send()
    except Exception as e:
        if not fail_silently:
            raise
        print(f"Failed to send email to {to_email}: {str(e)}")
        return 0


def send_teacher_invitation(invitation):
    """
    Send invitation email to a teacher.

    Args:
        invitation: UserInvitation model instance
    """
    invitation_url = f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')}/accept-invitation/{invitation.token}"

    # Get school name from database
    school_settings = get_school_settings()
    school_name = school_settings['school_name']

    context = {
        'recipient_name': f"{invitation.first_name} {invitation.last_name}",
        'invitation_url': invitation_url,
        'invitation': invitation,
        'days_until_expiry': invitation.days_until_expiry,
    }

    return send_email(
        subject=f"Invitation to Join {school_name} as a Teacher",
        to_email=invitation.email,
        template_name='invitation_teacher',
        context=context
    )


def send_parent_invitation(invitation):
    """
    Send invitation email to a parent.

    Args:
        invitation: UserInvitation model instance
    """
    invitation_url = f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')}/accept-invitation/{invitation.token}"

    # Get school name from database
    school_settings = get_school_settings()
    school_name = school_settings['school_name']

    context = {
        'recipient_name': f"{invitation.first_name} {invitation.last_name}",
        'invitation_url': invitation_url,
        'invitation': invitation,
        'days_until_expiry': invitation.days_until_expiry,
    }

    return send_email(
        subject=f"Parent Portal Invitation - {school_name}",
        to_email=invitation.email,
        template_name='invitation_parent',
        context=context
    )


def send_accountant_invitation(invitation):
    """
    Send invitation email to an accountant.

    Args:
        invitation: UserInvitation model instance
    """
    invitation_url = f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')}/accept-invitation/{invitation.token}"

    # Get school name from database
    school_settings = get_school_settings()
    school_name = school_settings['school_name']

    context = {
        'recipient_name': f"{invitation.first_name} {invitation.last_name}",
        'invitation_url': invitation_url,
        'invitation': invitation,
        'days_until_expiry': invitation.days_until_expiry,
    }

    return send_email(
        subject=f"Invitation to Join {school_name} - Finance Team",
        to_email=invitation.email,
        template_name='invitation_accountant',
        context=context
    )


def send_welcome_parent_email(parent, portal_url=None):
    """
    Send welcome email to a parent after account creation.

    Args:
        parent: Parent model instance
        portal_url: URL to the parent portal (optional)
    """
    if portal_url is None:
        portal_url = f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')}/parent/login"

    # Get school name from database
    school_settings = get_school_settings()
    school_name = school_settings['school_name']

    context = {
        'parent_name': f"{parent.first_name} {parent.last_name}",
        'recipient_email': parent.email,
        'portal_url': portal_url,
    }

    return send_email(
        subject=f"Welcome to {school_name} Parent Portal",
        to_email=parent.email,
        template_name='welcome_parent',
        context=context
    )


# ==================== ADMISSION EMAIL FUNCTIONS ====================

def send_admission_confirmation_email(application):
    """
    Send confirmation email after application submission.

    Args:
        application: AdmissionApplication model instance
    """
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    tracking_url = f"{frontend_url}/admissions/track/{application.tracking_token}"

    # Get school name and admissions contact from database
    school_settings = get_school_settings()

    context = {
        'parent_name': application.parent_guardian_name,
        'student_name': f"{application.first_name} {application.last_name}",
        'application_number': application.application_number,
        'class_level': application.class_level.name,
        'academic_session': str(application.session),
        'submission_date': application.submitted_at.strftime('%B %d, %Y') if application.submitted_at else application.created_at.strftime('%B %d, %Y'),
        'tracking_token': application.tracking_token,
        'tracking_url': tracking_url,
        'admissions_email': school_settings['contact_email'] or 'admissions@school.com',
        'admissions_phone': school_settings['contact_phone'] or 'N/A',
    }

    return send_email(
        subject=f"Application Received - {application.application_number}",
        to_email=application.email,
        template_name='admission_confirmation',
        context=context
    )


def send_admission_documents_required_email(application, required_documents=None, admin_notes=None, deadline=None):
    """
    Send email requesting additional documents.

    Args:
        application: AdmissionApplication model instance
        required_documents: List of document names required (optional)
        admin_notes: Additional notes from admin (optional)
        deadline: Deadline for document submission (optional)
    """
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    upload_url = f"{frontend_url}/admissions/track/{application.tracking_token}"

    # Get school name and admissions contact from database
    school_settings = get_school_settings()

    context = {
        'parent_name': application.parent_guardian_name,
        'student_name': f"{application.first_name} {application.last_name}",
        'application_number': application.application_number,
        'required_documents': required_documents,
        'admin_notes': admin_notes or application.admin_notes,
        'deadline': deadline,
        'upload_url': upload_url,
        'admissions_email': school_settings['contact_email'] or 'admissions@school.com',
        'admissions_phone': school_settings['contact_phone'] or 'N/A',
    }

    return send_email(
        subject=f"Documents Required - {application.application_number}",
        to_email=application.email,
        template_name='admission_documents_required',
        context=context
    )


def send_admission_exam_scheduled_email(application):
    """
    Send email with exam details.

    Args:
        application: AdmissionApplication model instance
    """
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    tracking_url = f"{frontend_url}/admissions/track/{application.tracking_token}"

    # Get school name and admissions contact from database
    school_settings = get_school_settings()

    # Get fee structure
    fee_structure = application.session.fee_structures.filter(
        class_level=application.class_level
    ).first()

    context = {
        'parent_name': application.parent_guardian_name,
        'student_name': f"{application.first_name} {application.last_name}",
        'application_number': application.application_number,
        'exam_date': application.exam_date.strftime('%A, %B %d, %Y') if application.exam_date else 'TBD',
        'exam_time': application.exam_time.strftime('%I:%M %p') if application.exam_time else 'TBD',
        'exam_venue': application.exam_venue or 'To be announced',
        'exam_fee_required': fee_structure.exam_fee_required if fee_structure else False,
        'exam_fee': fee_structure.exam_fee if fee_structure else 0,
        'exam_fee_paid': application.exam_fee_paid,
        'tracking_url': tracking_url,
        'admissions_email': school_settings['contact_email'] or 'admissions@school.com',
        'admissions_phone': school_settings['contact_phone'] or 'N/A',
    }

    return send_email(
        subject=f"Entrance Exam Scheduled - {application.application_number}",
        to_email=application.email,
        template_name='admission_exam_scheduled',
        context=context
    )


def send_admission_interview_scheduled_email(application):
    """
    Send email with interview details.

    Args:
        application: AdmissionApplication model instance
    """
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    tracking_url = f"{frontend_url}/admissions/track/{application.tracking_token}"

    # Get school name and admissions contact from database
    school_settings = get_school_settings()

    context = {
        'parent_name': application.parent_guardian_name,
        'student_name': f"{application.first_name} {application.last_name}",
        'application_number': application.application_number,
        'interview_date': application.interview_date.strftime('%A, %B %d, %Y') if application.interview_date else 'TBD',
        'interview_time': application.interview_time.strftime('%I:%M %p') if application.interview_time else 'TBD',
        'interview_venue': application.interview_venue or 'To be announced',
        'tracking_url': tracking_url,
        'admissions_email': school_settings['contact_email'] or 'admissions@school.com',
        'admissions_phone': school_settings['contact_phone'] or 'N/A',
    }

    return send_email(
        subject=f"Interview Scheduled - {application.application_number}",
        to_email=application.email,
        template_name='admission_interview_scheduled',
        context=context
    )


def send_admission_approved_email(application):
    """
    Send admission offer email.

    Args:
        application: AdmissionApplication model instance
    """
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    acceptance_url = f"{frontend_url}/admissions/track/{application.tracking_token}"

    # Get school name and admissions contact from database
    school_settings = get_school_settings()

    # Get fee structure
    fee_structure = application.session.fee_structures.filter(
        class_level=application.class_level
    ).first()

    context = {
        'parent_name': application.parent_guardian_name,
        'student_name': f"{application.first_name} {application.last_name}",
        'application_number': application.application_number,
        'class_level': application.class_level.name,
        'academic_session': str(application.session),
        'approval_notes': application.approval_notes,
        'acceptance_fee_required': fee_structure.acceptance_fee_required if fee_structure else False,
        'acceptance_fee': fee_structure.acceptance_fee if fee_structure else 0,
        'payment_instructions': 'Please contact the school office for payment instructions.',
        'offer_expiry_date': application.offer_expiry_date.strftime('%B %d, %Y') if application.offer_expiry_date else 'TBD',
        'acceptance_url': acceptance_url,
        'admissions_email': school_settings['contact_email'] or 'admissions@school.com',
        'admissions_phone': school_settings['contact_phone'] or 'N/A',
    }

    return send_email(
        subject=f"🎉 Admission Offer - {school_settings['school_name']}",
        to_email=application.email,
        template_name='admission_approved',
        context=context
    )


def send_admission_rejected_email(application):
    """
    Send application rejection email.

    Args:
        application: AdmissionApplication model instance
    """
    # Get school name and admissions contact from database
    school_settings = get_school_settings()

    context = {
        'parent_name': application.parent_guardian_name,
        'student_name': f"{application.first_name} {application.last_name}",
        'application_number': application.application_number,
        'class_level': application.class_level.name,
        'academic_session': str(application.session),
        'rejection_reason': application.rejection_reason,
        'admissions_email': school_settings['contact_email'] or 'admissions@school.com',
        'admissions_phone': school_settings['contact_phone'] or 'N/A',
    }

    return send_email(
        subject=f"Application Update - {application.application_number}",
        to_email=application.email,
        template_name='admission_rejected',
        context=context
    )


def send_admission_accepted_email(application):
    """
    Send confirmation email after offer acceptance.

    Args:
        application: AdmissionApplication model instance
    """
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    tracking_url = f"{frontend_url}/admissions/track/{application.tracking_token}"

    # Get school name and admissions contact from database
    school_settings = get_school_settings()

    context = {
        'parent_name': application.parent_guardian_name,
        'student_name': f"{application.first_name} {application.last_name}",
        'application_number': application.application_number,
        'class_level': application.class_level.name,
        'academic_session': str(application.session),
        'tracking_url': tracking_url,
        'resumption_date': None,  # To be set based on academic calendar
        'document_deadline': None,  # To be set based on school policy
        'admissions_email': school_settings['contact_email'] or 'admissions@school.com',
        'admissions_phone': school_settings['contact_phone'] or 'N/A',
    }

    return send_email(
        subject=f"🎊 Welcome to {school_settings['school_name']}!",
        to_email=application.email,
        template_name='admission_accepted',
        context=context
    )


def send_admission_enrolled_email(application):
    """
    Send enrollment confirmation email with student credentials.

    Args:
        application: AdmissionApplication model instance
    """
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    portal_url = f"{frontend_url}/student/login"

    # Get school name and contact from database
    school_settings = get_school_settings()

    context = {
        'parent_name': application.parent_guardian_name,
        'student_name': f"{application.first_name} {application.last_name}",
        'student_id': application.student.id if application.student else 'TBD',
        'application_number': application.application_number,
        'class_level': application.class_level.name,
        'academic_session': str(application.session),
        'portal_url': portal_url,
        'username': application.student.user.username if application.student else 'TBD',
        'temporary_password': 'ChangeMe123!',  # Default password set during enrollment
        'orientation_date': None,  # To be set based on school calendar
        'resumption_date': None,  # To be set based on school calendar
        'first_day_assembly': '8:00 AM on resumption day',
        'school_phone': school_settings['contact_phone'] or 'N/A',
        'school_email': school_settings['contact_email'] or 'info@school.com',
        'school_address': school_settings['address'] or 'N/A',
        'admissions_email': school_settings['contact_email'] or 'admissions@school.com',
        'admissions_phone': school_settings['contact_phone'] or 'N/A',
    }

    return send_email(
        subject=f"🎓 Enrollment Complete - Welcome to {school_settings['school_name']}!",
        to_email=application.email,
        template_name='admission_enrolled',
        context=context
    )
