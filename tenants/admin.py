from django.contrib import admin
from .models import SchoolSettings


@admin.register(SchoolSettings)
class SchoolSettingsAdmin(admin.ModelAdmin):
    list_display = [
        'school_name',
        'onboarding_completed',
        'admin_user',
        'contact_email',
        'created_at'
    ]
    list_filter = ['onboarding_completed', 'created_at']
    search_fields = ['school_name', 'contact_email']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Basic Information', {
            'fields': ('school_name', 'logo')
        }),
        ('Onboarding', {
            'fields': ('onboarding_step', 'onboarding_completed', 'admin_user')
        }),
        ('Branding', {
            'fields': ('primary_color', 'secondary_color'),
            'classes': ('collapse',)
        }),
        ('Contact Information', {
            'fields': ('address', 'contact_email', 'contact_phone')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('admin_user')

    def has_add_permission(self, request):
        # Only allow one SchoolSettings instance
        return not SchoolSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Prevent deletion of school settings
        return False
