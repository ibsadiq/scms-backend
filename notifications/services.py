"""
Notification Service - Phase 1.5: Automated Notifications System

Handles:
- Email sending (SMTP/SendGrid)
- SMS sending (Twilio/Africa's Talking)
- Template rendering with variables
- Preference checking
- Batch sending for daily digests
"""
import logging
from typing import Dict, List, Optional, Any
from django.core.mail import send_mail, EmailMessage
from django.template import Template, Context
from django.conf import settings
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType

from .models import Notification, NotificationPreference, NotificationTemplate
from users.models import CustomUser
from academic.models import Student

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Service for creating and sending notifications.

    Supports:
    - In-app notifications
    - Email delivery
    - SMS delivery (with integration placeholders)
    - Template rendering
    - User preference checking
    """

    def __init__(self):
        """Initialize notification service"""
        self.email_from = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@school.com')
        self.sms_enabled = getattr(settings, 'SMS_ENABLED', False)

    def create_notification(
        self,
        recipient: CustomUser,
        notification_type: str,
        title: str,
        message: str,
        priority: str = 'normal',
        related_student: Optional[Student] = None,
        related_object: Optional[Any] = None,
        send_email: bool = True,
        send_sms: bool = False,
        expires_at: Optional[timezone.datetime] = None
    ) -> Notification:
        """
        Create a notification record.

        Args:
            recipient: User to receive notification
            notification_type: Type of notification (attendance, fee, result, etc.)
            title: Notification title
            message: Notification message
            priority: Priority level (low, normal, high, urgent)
            related_student: Student this notification is about (for parents)
            related_object: Any related object (exam, event, etc.)
            send_email: Whether to send email
            send_sms: Whether to send SMS
            expires_at: When notification expires (optional)

        Returns:
            Created Notification instance
        """
        # Get or create notification preferences
        prefs, _ = NotificationPreference.objects.get_or_create(user=recipient)

        # Create notification record
        notification = Notification.objects.create(
            recipient=recipient,
            related_student=related_student,
            notification_type=notification_type,
            priority=priority,
            title=title,
            message=message,
            expires_at=expires_at
        )

        # Set related object if provided
        if related_object:
            notification.content_type = ContentType.objects.get_for_model(related_object)
            notification.object_id = related_object.id
            notification.save()

        # Check preferences and send
        if send_email and prefs.should_send_email(notification_type, priority):
            self.send_email_notification(notification)

        if send_sms and prefs.should_send_sms(notification_type, priority):
            self.send_sms_notification(notification)

        return notification

    def create_notification_from_template(
        self,
        recipient: CustomUser,
        notification_type: str,
        context_data: Dict[str, Any],
        priority: str = 'normal',
        related_student: Optional[Student] = None,
        related_object: Optional[Any] = None,
        send_email: bool = True,
        send_sms: bool = False
    ) -> Notification:
        """
        Create notification using a template.

        Args:
            recipient: User to receive notification
            notification_type: Type of notification
            context_data: Variables for template rendering
            priority: Priority level
            related_student: Student this notification is about
            related_object: Related object
            send_email: Whether to send email
            send_sms: Whether to send SMS

        Returns:
            Created Notification instance
        """
        try:
            template = NotificationTemplate.objects.get(
                template_type=notification_type,
                is_active=True
            )
        except NotificationTemplate.DoesNotExist:
            logger.error(f"No active template found for type: {notification_type}")
            raise ValueError(f"No template available for notification type: {notification_type}")

        # Render title and message
        title = self._render_template(template.title_template, context_data)
        message = self._render_template(template.message_template, context_data)

        return self.create_notification(
            recipient=recipient,
            notification_type=notification_type,
            title=title,
            message=message,
            priority=priority,
            related_student=related_student,
            related_object=related_object,
            send_email=send_email,
            send_sms=send_sms
        )

    def send_email_notification(self, notification: Notification) -> bool:
        """
        Send email for a notification.

        Args:
            notification: Notification instance

        Returns:
            True if sent successfully, False otherwise
        """
        if not notification.recipient.email:
            notification.email_error = "Recipient has no email address"
            notification.save()
            return False

        try:
            # Get template if available
            try:
                template = NotificationTemplate.objects.get(
                    template_type=notification.notification_type,
                    is_active=True
                )
                subject = template.email_subject_template
                body = template.email_body_template

                # Render with notification context
                context = self._get_notification_context(notification)
                subject = self._render_template(subject, context)
                body = self._render_template(body, context)
            except NotificationTemplate.DoesNotExist:
                # Fallback to notification title/message
                subject = notification.title
                body = notification.message

            # Send email
            send_mail(
                subject=subject,
                message=body,
                from_email=self.email_from,
                recipient_list=[notification.recipient.email],
                fail_silently=False
            )

            # Update notification
            notification.sent_via_email = True
            notification.email_sent_at = timezone.now()
            notification.save(update_fields=['sent_via_email', 'email_sent_at'])

            logger.info(f"Email sent successfully to {notification.recipient.email} for notification {notification.id}")
            return True

        except Exception as e:
            error_msg = f"Failed to send email: {str(e)}"
            notification.email_error = error_msg
            notification.save(update_fields=['email_error'])
            logger.error(f"Email sending failed for notification {notification.id}: {error_msg}")
            return False

    def send_sms_notification(self, notification: Notification) -> bool:
        """
        Send SMS for a notification.

        Args:
            notification: Notification instance

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.sms_enabled:
            notification.sms_error = "SMS service is not enabled"
            notification.save()
            return False

        # Get phone number
        phone_number = self._get_user_phone_number(notification.recipient)
        if not phone_number:
            notification.sms_error = "Recipient has no phone number"
            notification.save()
            return False

        try:
            # Get template if available
            try:
                template = NotificationTemplate.objects.get(
                    template_type=notification.notification_type,
                    is_active=True
                )
                message = template.sms_template

                # Render with notification context
                context = self._get_notification_context(notification)
                message = self._render_template(message, context)
            except NotificationTemplate.DoesNotExist:
                # Fallback to notification message (truncated to 160 chars)
                message = notification.message[:160]

            # Send SMS via provider
            success = self._send_sms_via_provider(phone_number, message)

            if success:
                notification.sent_via_sms = True
                notification.sms_sent_at = timezone.now()
                notification.save(update_fields=['sent_via_sms', 'sms_sent_at'])
                logger.info(f"SMS sent successfully to {phone_number} for notification {notification.id}")
                return True
            else:
                notification.sms_error = "SMS provider returned failure"
                notification.save()
                return False

        except Exception as e:
            error_msg = f"Failed to send SMS: {str(e)}"
            notification.sms_error = error_msg
            notification.save(update_fields=['sms_error'])
            logger.error(f"SMS sending failed for notification {notification.id}: {error_msg}")
            return False

    def send_bulk_notifications(
        self,
        recipients: List[CustomUser],
        notification_type: str,
        title: str,
        message: str,
        priority: str = 'normal',
        send_email: bool = True,
        send_sms: bool = False
    ) -> Dict[str, int]:
        """
        Send the same notification to multiple recipients.

        Args:
            recipients: List of users to notify
            notification_type: Type of notification
            title: Notification title
            message: Notification message
            priority: Priority level
            send_email: Whether to send email
            send_sms: Whether to send SMS

        Returns:
            Dictionary with counts: {'created': X, 'email_sent': Y, 'sms_sent': Z, 'errors': W}
        """
        results = {
            'created': 0,
            'email_sent': 0,
            'sms_sent': 0,
            'errors': 0
        }

        for recipient in recipients:
            try:
                notification = self.create_notification(
                    recipient=recipient,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    priority=priority,
                    send_email=send_email,
                    send_sms=send_sms
                )
                results['created'] += 1

                if notification.sent_via_email:
                    results['email_sent'] += 1

                if notification.sent_via_sms:
                    results['sms_sent'] += 1

            except Exception as e:
                logger.error(f"Failed to create notification for {recipient.username}: {str(e)}")
                results['errors'] += 1

        return results

    def send_daily_digest(self, user: CustomUser) -> bool:
        """
        Send daily digest email with all unread notifications.

        Args:
            user: User to send digest to

        Returns:
            True if sent successfully, False otherwise
        """
        # Get user preferences
        try:
            prefs = NotificationPreference.objects.get(user=user)
        except NotificationPreference.DoesNotExist:
            logger.warning(f"No preferences found for user {user.username}")
            return False

        if not prefs.daily_digest:
            return False

        # Get unread notifications from today
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        notifications = Notification.objects.filter(
            recipient=user,
            is_read=False,
            created_at__gte=today_start
        ).order_by('-created_at')

        if not notifications.exists():
            return False  # Nothing to send

        # Build digest email
        subject = f"Daily Digest - {notifications.count()} New Notifications"

        body_parts = [
            f"Hello {user.get_full_name() or user.username},\n",
            f"\nYou have {notifications.count()} unread notifications:\n\n"
        ]

        for notif in notifications:
            body_parts.append(f"[{notif.get_priority_display()}] {notif.title}\n")
            body_parts.append(f"{notif.message}\n")
            body_parts.append(f"Time: {notif.created_at.strftime('%I:%M %p')}\n\n")

        body_parts.append("\nLog in to view full details.\n")
        body = ''.join(body_parts)

        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=self.email_from,
                recipient_list=[user.email],
                fail_silently=False
            )
            logger.info(f"Daily digest sent to {user.email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send daily digest to {user.email}: {str(e)}")
            return False

    def _render_template(self, template_string: str, context_data: Dict[str, Any]) -> str:
        """
        Render a Django template string with context.

        Args:
            template_string: Template string with {{ variables }}
            context_data: Dictionary of variables

        Returns:
            Rendered string
        """
        try:
            template = Template(template_string)
            context = Context(context_data)
            return template.render(context)
        except Exception as e:
            logger.error(f"Template rendering failed: {str(e)}")
            return template_string  # Return unrendered on error

    def _get_notification_context(self, notification: Notification) -> Dict[str, Any]:
        """
        Build context dictionary for notification template rendering.

        Args:
            notification: Notification instance

        Returns:
            Dictionary with variables for template
        """
        context = {
            'recipient_name': notification.recipient.get_full_name() or notification.recipient.username,
            'recipient_username': notification.recipient.username,
            'notification_title': notification.title,
            'notification_message': notification.message,
            'notification_type': notification.get_notification_type_display(),
            'priority': notification.get_priority_display(),
            'created_at': notification.created_at,
        }

        # Add student info if available
        if notification.related_student:
            context.update({
                'student_name': notification.related_student.full_name,
                'student_admission_number': notification.related_student.admission_number,
                'student_class': str(notification.related_student.classroom) if notification.related_student.classroom else 'N/A',
            })

        return context

    def _get_user_phone_number(self, user: CustomUser) -> Optional[str]:
        """
        Get user's phone number from various sources.

        Args:
            user: User instance

        Returns:
            Phone number string or None
        """
        # Check if user has phone_number field
        if hasattr(user, 'phone_number') and user.phone_number:
            return user.phone_number

        # Check if user is a parent
        if hasattr(user, 'parent') and user.parent.phone_number:
            return user.parent.phone_number

        # Check if user is a teacher
        if hasattr(user, 'teacher') and user.teacher.phone_number:
            return user.teacher.phone_number

        return None

    def _send_sms_via_provider(self, phone_number: str, message: str) -> bool:
        """
        Send SMS via external provider (Twilio, Africa's Talking, etc.).

        This is a placeholder. Implement based on your SMS provider.

        Args:
            phone_number: Recipient phone number
            message: SMS message

        Returns:
            True if sent successfully, False otherwise
        """
        # TODO: Implement SMS provider integration
        # Example for Twilio:
        # from twilio.rest import Client
        # client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        # message = client.messages.create(
        #     body=message,
        #     from_=settings.TWILIO_PHONE_NUMBER,
        #     to=phone_number
        # )
        # return message.sid is not None

        # Example for Africa's Talking:
        # import africastalking
        # africastalking.initialize(settings.AT_USERNAME, settings.AT_API_KEY)
        # sms = africastalking.SMS
        # response = sms.send(message, [phone_number])
        # return response['SMSMessageData']['Recipients'][0]['status'] == 'Success'

        logger.warning(f"SMS provider not configured. Would send to {phone_number}: {message}")
        return False  # Return False since provider is not configured
