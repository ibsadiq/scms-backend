"""
Notification Serializers - Phase 1.5: Automated Notifications System
"""
from rest_framework import serializers
from .models import Notification, NotificationPreference, NotificationTemplate


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for Notification model"""

    notification_type_display = serializers.CharField(
        source='get_notification_type_display',
        read_only=True
    )
    priority_display = serializers.CharField(
        source='get_priority_display',
        read_only=True
    )
    delivery_status = serializers.ReadOnlyField()
    is_expired = serializers.ReadOnlyField()

    # Related fields
    recipient_name = serializers.CharField(
        source='recipient.get_full_name',
        read_only=True
    )
    student_name = serializers.CharField(
        source='related_student.full_name',
        read_only=True,
        allow_null=True
    )
    student_admission_number = serializers.CharField(
        source='related_student.admission_number',
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = Notification
        fields = [
            'id',
            'recipient',
            'recipient_name',
            'related_student',
            'student_name',
            'student_admission_number',
            'notification_type',
            'notification_type_display',
            'priority',
            'priority_display',
            'title',
            'message',
            'is_read',
            'read_at',
            'sent_via_email',
            'email_sent_at',
            'email_error',
            'sent_via_sms',
            'sms_sent_at',
            'sms_error',
            'created_at',
            'expires_at',
            'delivery_status',
            'is_expired',
        ]
        read_only_fields = [
            'id',
            'recipient',
            'created_at',
            'read_at',
            'email_sent_at',
            'sms_sent_at',
        ]


class NotificationCreateSerializer(serializers.Serializer):
    """Serializer for creating notifications via API"""

    recipient_id = serializers.IntegerField(help_text="User ID to receive notification")
    notification_type = serializers.ChoiceField(
        choices=Notification.NOTIFICATION_TYPES,
        help_text="Type of notification"
    )
    title = serializers.CharField(max_length=200, help_text="Notification title")
    message = serializers.CharField(help_text="Notification message")
    priority = serializers.ChoiceField(
        choices=Notification.PRIORITY_LEVELS,
        default='normal',
        help_text="Priority level"
    )
    related_student_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="Student ID this notification is about (optional)"
    )
    send_email = serializers.BooleanField(
        default=True,
        help_text="Send email notification"
    )
    send_sms = serializers.BooleanField(
        default=False,
        help_text="Send SMS notification"
    )
    expires_at = serializers.DateTimeField(
        required=False,
        allow_null=True,
        help_text="When notification expires (optional)"
    )


class BulkNotificationSerializer(serializers.Serializer):
    """Serializer for sending bulk notifications"""

    recipient_ids = serializers.ListField(
        child=serializers.IntegerField(),
        help_text="List of user IDs to receive notification"
    )
    notification_type = serializers.ChoiceField(
        choices=Notification.NOTIFICATION_TYPES,
        help_text="Type of notification"
    )
    title = serializers.CharField(max_length=200, help_text="Notification title")
    message = serializers.CharField(help_text="Notification message")
    priority = serializers.ChoiceField(
        choices=Notification.PRIORITY_LEVELS,
        default='normal',
        help_text="Priority level"
    )
    send_email = serializers.BooleanField(
        default=True,
        help_text="Send email notifications"
    )
    send_sms = serializers.BooleanField(
        default=False,
        help_text="Send SMS notifications"
    )


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """Serializer for NotificationPreference model"""

    user_name = serializers.CharField(
        source='user.get_full_name',
        read_only=True
    )

    class Meta:
        model = NotificationPreference
        fields = [
            'id',
            'user',
            'user_name',
            'email_enabled',
            'email_attendance',
            'email_fees',
            'email_results',
            'email_exams',
            'email_events',
            'email_promotions',
            'email_report_cards',
            'sms_enabled',
            'sms_attendance',
            'sms_fees',
            'sms_results',
            'sms_urgent_only',
            'daily_digest',
            'digest_time',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']


class NotificationTemplateSerializer(serializers.ModelSerializer):
    """Serializer for NotificationTemplate model"""

    template_type_display = serializers.CharField(
        source='get_template_type_display',
        read_only=True
    )

    class Meta:
        model = NotificationTemplate
        fields = [
            'id',
            'template_type',
            'template_type_display',
            'email_subject_template',
            'email_body_template',
            'sms_template',
            'title_template',
            'message_template',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
