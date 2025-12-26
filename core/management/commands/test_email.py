"""
Management command to test email functionality with Mailpit
"""
from django.core.management.base import BaseCommand
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.utils.html import strip_tags


class Command(BaseCommand):
    help = 'Send test emails to verify Mailpit configuration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--email',
            type=str,
            default='test@example.com',
            help='Recipient email address'
        )
        parser.add_argument(
            '--type',
            type=str,
            choices=['simple', 'formatted', 'notification', 'absence'],
            default='formatted',
            help='Type of test email to send'
        )

    def handle(self, *args, **options):
        recipient = options['email']
        email_type = options['type']

        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(self.style.SUCCESS('📧 Email System Test'))
        self.stdout.write(f"{'='*60}\n")

        # Display configuration
        self.stdout.write(f"Backend: {settings.EMAIL_BACKEND}")
        self.stdout.write(f"Host: {settings.EMAIL_HOST}:{settings.EMAIL_PORT}")
        self.stdout.write(f"From: {settings.DEFAULT_FROM_EMAIL}")
        self.stdout.write(f"To: {recipient}\n")

        if email_type == 'simple':
            self.send_simple_email(recipient)
        elif email_type == 'formatted':
            self.send_formatted_email(recipient)
        elif email_type == 'notification':
            self.send_notification_email(recipient)
        elif email_type == 'absence':
            self.send_absence_notification(recipient)

        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(self.style.SUCCESS('✅ Email sent successfully!'))
        self.stdout.write(self.style.WARNING('🔍 Check Mailpit at http://localhost:8025'))
        self.stdout.write(f"{'='*60}\n")

    def send_simple_email(self, recipient):
        """Send a simple plain text email"""
        from django.core.mail import send_mail

        send_mail(
            subject='Simple Test Email',
            message='This is a plain text test email from Django SCMS.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
        self.stdout.write(self.style.SUCCESS('✓ Simple email sent'))

    def send_formatted_email(self, recipient):
        """Send a formatted HTML email using template"""
        from django.template.loader import render_to_string

        # Get app name and school name from settings
        app_name = getattr(settings, 'APP_NAME', 'SCMS')
        school_name = getattr(settings, 'SCHOOL_NAME', 'School Management System')

        # Context for template
        context = {
            'app_name': app_name,
            'school_name': school_name,
            'parent_name': 'John Doe',  # In real use, this would be the actual parent name
            'recipient_email': recipient,
            'portal_url': 'http://localhost:3000/login',
        }

        subject = f'🎓 Welcome to {app_name}'

        # Render both plain text and HTML versions from templates
        text_content = render_to_string('email/welcome_parent.txt', context)
        html_content = render_to_string('email/welcome_parent.html', context)

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient]
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send()

        self.stdout.write(self.style.SUCCESS('✓ Formatted HTML email sent'))

    def send_notification_email(self, recipient):
        """Send a fee payment reminder email"""
        from django.template.loader import render_to_string
        from datetime import date, timedelta

        # Get app name and school name from settings
        app_name = getattr(settings, 'APP_NAME', 'SCMS')
        school_name = getattr(settings, 'SCHOOL_NAME', 'School Management System')

        # Context for template
        context = {
            'app_name': app_name,
            'school_name': school_name,
            'parent_name': 'Mr. John Doe',
            'student_name': 'Sarah Doe',
            'amount': 'UGX 500,000',
            'due_date': (date.today() + timedelta(days=14)).strftime('%B %d, %Y'),
            'term_name': 'Term 1, 2025',
            'portal_url': 'http://localhost:3000/parent/fees',
        }

        subject = f'🔔 Fee Payment Reminder - {context["term_name"]}'

        # Render both plain text and HTML versions from templates
        text_content = render_to_string('email/fee_reminder.txt', context)
        html_content = render_to_string('email/fee_reminder.html', context)

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient]
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send()

        self.stdout.write(self.style.SUCCESS('✓ Fee reminder email sent'))

    def send_absence_notification(self, recipient):
        """Send an absence notification email"""
        from django.template.loader import render_to_string
        from datetime import date

        # Get app name and school name from settings
        app_name = getattr(settings, 'APP_NAME', 'SCMS')
        school_name = getattr(settings, 'SCHOOL_NAME', 'School Management System')

        # Context for template
        context = {
            'app_name': app_name,
            'school_name': school_name,
            'parent_name': 'Mr. John Doe',
            'student_name': 'Sarah Doe',
            'class_name': 'Primary 4A',
            'date': date.today().strftime('%B %d, %Y'),
            'status': 'Absent',
            'remarks': 'Did not attend morning assembly and all classes',
            'portal_url': 'http://localhost:3000/parent/attendance',
        }

        subject = f'🔔 Absence Notification - {context["student_name"]}'

        # Render both plain text and HTML versions from templates
        text_content = render_to_string('email/absence_notification.txt', context)
        html_content = render_to_string('email/absence_notification.html', context)

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient]
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send()

        self.stdout.write(self.style.SUCCESS('✓ Absence notification email sent'))
