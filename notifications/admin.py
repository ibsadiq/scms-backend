"""
Notification Admin - Phase 1.5: Automated Notifications System
"""
from django.contrib import admin
from .models import Notification, NotificationPreference, NotificationTemplate


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Admin interface for Notification model"""

    list_display = [
        'id',
        'recipient',
        'notification_type',
        'priority',
        'title',
        'is_read',
        'sent_via_email',
        'sent_via_sms',
        'created_at',
    ]

    list_filter = [
        'notification_type',
        'priority',
        'is_read',
        'sent_via_email',
        'sent_via_sms',
        'created_at',
    ]

    search_fields = [
        'recipient__username',
        'recipient__email',
        'recipient__first_name',
        'recipient__last_name',
        'title',
        'message',
        'related_student__first_name',
        'related_student__last_name',
        'related_student__admission_number',
    ]

    readonly_fields = [
        'created_at',
        'read_at',
        'email_sent_at',
        'sms_sent_at',
        'delivery_status',
        'is_expired',
    ]

    fieldsets = (
        ('Recipient', {
            'fields': ('recipient', 'related_student')
        }),
        ('Notification Details', {
            'fields': ('notification_type', 'priority', 'title', 'message', 'expires_at')
        }),
        ('Read Status', {
            'fields': ('is_read', 'read_at')
        }),
        ('Email Delivery', {
            'fields': ('sent_via_email', 'email_sent_at', 'email_error'),
            'classes': ('collapse',)
        }),
        ('SMS Delivery', {
            'fields': ('sent_via_sms', 'sms_sent_at', 'sms_error'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'delivery_status', 'is_expired'),
            'classes': ('collapse',)
        }),
    )

    date_hierarchy = 'created_at'

    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related('recipient', 'related_student')


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    """Admin interface for NotificationPreference model"""

    list_display = [
        'id',
        'user',
        'email_enabled',
        'sms_enabled',
        'daily_digest',
        'updated_at',
    ]

    list_filter = [
        'email_enabled',
        'sms_enabled',
        'daily_digest',
        'sms_urgent_only',
    ]

    search_fields = [
        'user__username',
        'user__email',
        'user__first_name',
        'user__last_name',
    ]

    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Email Preferences', {
            'fields': (
                'email_enabled',
                'email_attendance',
                'email_fees',
                'email_results',
                'email_exams',
                'email_events',
                'email_promotions',
                'email_report_cards',
            )
        }),
        ('SMS Preferences', {
            'fields': (
                'sms_enabled',
                'sms_attendance',
                'sms_fees',
                'sms_results',
                'sms_urgent_only',
            )
        }),
        ('Digest Options', {
            'fields': ('daily_digest', 'digest_time')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related('user')


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    """Admin interface for NotificationTemplate model"""

    list_display = [
        'id',
        'template_type',
        'is_active',
        'updated_at',
    ]

    list_filter = [
        'template_type',
        'is_active',
    ]

    search_fields = [
        'template_type',
        'email_subject_template',
        'email_body_template',
        'title_template',
        'message_template',
    ]

    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Template Type', {
            'fields': ('template_type', 'is_active')
        }),
        ('Email Templates', {
            'fields': ('email_subject_template', 'email_body_template')
        }),
        ('SMS Template', {
            'fields': ('sms_template',)
        }),
        ('In-App Notification Template', {
            'fields': ('title_template', 'message_template')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        """Add help text to form fields"""
        form = super().get_form(request, obj, **kwargs)

        # Add help text for template variables
        help_texts = {
            'email_subject_template': 'Use variables like {{recipient_name}}, {{student_name}}, etc.',
            'email_body_template': 'Use variables like {{recipient_name}}, {{student_name}}, {{notification_message}}, etc.',
            'sms_template': 'Max 160 characters. Use variables like {{student_name}}, {{recipient_name}}.',
            'title_template': 'Use variables like {{student_name}}, {{recipient_name}}.',
            'message_template': 'Use variables like {{student_name}}, {{notification_message}}.',
        }

        for field, help_text in help_texts.items():
            if field in form.base_fields:
                form.base_fields[field].help_text = help_text

        return form
