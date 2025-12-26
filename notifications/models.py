"""
Notification Models - Phase 1.5: Automated Notifications System

Handles:
- In-app notifications
- Email notifications
- SMS notifications
- User notification preferences
- Notification history and tracking
"""
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from users.models import CustomUser
from academic.models import Student


class Notification(models.Model):
    """
    Stores notification records for users.

    Supports multiple notification types and delivery channels.
    Uses Generic Foreign Key to link to any related object.
    """

    NOTIFICATION_TYPES = [
        ('attendance', 'Attendance Alert'),
        ('fee', 'Fee Reminder'),
        ('result', 'Result Published'),
        ('exam', 'Upcoming Exam'),
        ('event', 'School Event'),
        ('promotion', 'Promotion Decision'),
        ('report_card', 'Report Card Available'),
        ('assignment', 'Assignment Notification'),  # Phase 1.6: Assignment support
        ('general', 'General Announcement'),
    ]

    PRIORITY_LEVELS = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    # Recipients
    recipient = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='notifications',
        help_text="User who receives this notification"
    )
    related_student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
        help_text="Student this notification is about (for parents)"
    )

    # Notification Content
    notification_type = models.CharField(
        max_length=20,
        choices=NOTIFICATION_TYPES,
        help_text="Type of notification"
    )
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_LEVELS,
        default='normal'
    )
    title = models.CharField(
        max_length=200,
        help_text="Notification title/subject"
    )
    message = models.TextField(
        help_text="Full notification message"
    )

    # Related Object (Generic FK for flexibility)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    object_id = models.PositiveIntegerField(
        null=True,
        blank=True
    )
    related_object = GenericForeignKey('content_type', 'object_id')

    # Delivery Status
    is_read = models.BooleanField(
        default=False,
        help_text="Whether user has read this notification"
    )
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When notification was read"
    )

    sent_via_email = models.BooleanField(
        default=False,
        help_text="Whether email was sent"
    )
    email_sent_at = models.DateTimeField(
        null=True,
        blank=True
    )
    email_error = models.TextField(
        blank=True,
        help_text="Email delivery error message if any"
    )

    sent_via_sms = models.BooleanField(
        default=False,
        help_text="Whether SMS was sent"
    )
    sms_sent_at = models.DateTimeField(
        null=True,
        blank=True
    )
    sms_error = models.TextField(
        blank=True,
        help_text="SMS delivery error message if any"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this notification expires (optional)"
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', '-created_at']),
            models.Index(fields=['recipient', 'is_read']),
            models.Index(fields=['notification_type', '-created_at']),
        ]
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"

    def __str__(self):
        return f"{self.get_notification_type_display()} for {self.recipient.username} - {self.title}"

    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

    @property
    def is_expired(self):
        """Check if notification has expired"""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False

    @property
    def delivery_status(self):
        """Get overall delivery status"""
        statuses = []
        if self.sent_via_email:
            statuses.append('email')
        if self.sent_via_sms:
            statuses.append('sms')
        if not statuses:
            statuses.append('in-app only')
        return ', '.join(statuses)


class NotificationPreference(models.Model):
    """
    User preferences for notification delivery channels.

    Controls which notification types trigger emails/SMS.
    """

    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='notification_preferences'
    )

    # Email Preferences
    email_enabled = models.BooleanField(
        default=True,
        help_text="Enable email notifications"
    )
    email_attendance = models.BooleanField(
        default=True,
        help_text="Email for attendance alerts"
    )
    email_fees = models.BooleanField(
        default=True,
        help_text="Email for fee reminders"
    )
    email_results = models.BooleanField(
        default=True,
        help_text="Email when results are published"
    )
    email_exams = models.BooleanField(
        default=True,
        help_text="Email for upcoming exams"
    )
    email_events = models.BooleanField(
        default=True,
        help_text="Email for school events"
    )
    email_promotions = models.BooleanField(
        default=True,
        help_text="Email for promotion decisions"
    )
    email_report_cards = models.BooleanField(
        default=True,
        help_text="Email when report cards are ready"
    )
    email_assignments = models.BooleanField(
        default=True,
        help_text="Email for assignment notifications (Phase 1.6)"
    )

    # SMS Preferences (typically more selective due to cost)
    sms_enabled = models.BooleanField(
        default=False,
        help_text="Enable SMS notifications"
    )
    sms_attendance = models.BooleanField(
        default=False,
        help_text="SMS for attendance alerts"
    )
    sms_fees = models.BooleanField(
        default=True,
        help_text="SMS for fee reminders"
    )
    sms_results = models.BooleanField(
        default=False,
        help_text="SMS when results are published"
    )
    sms_urgent_only = models.BooleanField(
        default=True,
        help_text="Only send SMS for urgent notifications"
    )

    # Digest Options
    daily_digest = models.BooleanField(
        default=False,
        help_text="Receive daily digest email instead of individual emails"
    )
    digest_time = models.TimeField(
        default='18:00:00',
        help_text="Time to send daily digest (default 6 PM)"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Notification Preference"
        verbose_name_plural = "Notification Preferences"

    def __str__(self):
        return f"Notification preferences for {self.user.username}"

    def should_send_email(self, notification_type: str, priority: str = 'normal') -> bool:
        """
        Check if email should be sent for this notification type.

        Args:
            notification_type: Type of notification
            priority: Priority level

        Returns:
            Boolean indicating if email should be sent
        """
        if not self.email_enabled:
            return False

        if self.daily_digest and priority != 'urgent':
            return False  # Will be included in digest

        type_mapping = {
            'attendance': self.email_attendance,
            'fee': self.email_fees,
            'result': self.email_results,
            'exam': self.email_exams,
            'event': self.email_events,
            'promotion': self.email_promotions,
            'report_card': self.email_report_cards,
            'assignment': self.email_assignments,  # Phase 1.6
            'general': True,  # Always send general announcements
        }

        return type_mapping.get(notification_type, False)

    def should_send_sms(self, notification_type: str, priority: str = 'normal') -> bool:
        """
        Check if SMS should be sent for this notification type.

        Args:
            notification_type: Type of notification
            priority: Priority level

        Returns:
            Boolean indicating if SMS should be sent
        """
        if not self.sms_enabled:
            return False

        if self.sms_urgent_only and priority != 'urgent':
            return False

        type_mapping = {
            'attendance': self.sms_attendance,
            'fee': self.sms_fees,
            'result': self.sms_results,
        }

        return type_mapping.get(notification_type, False)


class NotificationTemplate(models.Model):
    """
    Templates for notification messages.

    Supports variables for personalization using Django template syntax.
    """

    TEMPLATE_TYPES = [
        ('attendance', 'Attendance Alert'),
        ('fee', 'Fee Reminder'),
        ('result', 'Result Published'),
        ('exam', 'Upcoming Exam'),
        ('event', 'School Event'),
        ('promotion', 'Promotion Decision'),
        ('report_card', 'Report Card Available'),
        ('assignment', 'Assignment Notification'),  # Phase 1.6
        ('general', 'General Announcement'),
    ]

    template_type = models.CharField(
        max_length=20,
        choices=TEMPLATE_TYPES,
        unique=True
    )

    # Email Template
    email_subject_template = models.CharField(
        max_length=200,
        help_text="Email subject with variables like {{student_name}}"
    )
    email_body_template = models.TextField(
        help_text="Email body with variables"
    )

    # SMS Template (shorter)
    sms_template = models.CharField(
        max_length=160,
        help_text="SMS message (max 160 chars) with variables"
    )

    # In-app notification template
    title_template = models.CharField(
        max_length=200,
        help_text="Notification title with variables"
    )
    message_template = models.TextField(
        help_text="Notification message with variables"
    )

    # Metadata
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Notification Template"
        verbose_name_plural = "Notification Templates"

    def __str__(self):
        return f"{self.get_template_type_display()} Template"
