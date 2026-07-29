# tenants/admin.py

from django.contrib import admin
from django.utils.html import format_html
from .models import Client, Domain, TenantStatus


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'schema_name',
        'plan_badge',
        'status_badge',
        'primary_domain',
        'cached_student_count',  # read from cached field — no cross-schema query
        'cached_teacher_count',
        'created_on',
        'onboarding_completed',
    ]
    list_filter  = ['status', 'has_mobile_access', 'created_on']
    search_fields = ['name', 'schema_name', 'contact_email']
    readonly_fields = [
        'schema_name',
        'created_on',
        'mobile_access_granted',
        'cached_student_count',
        'cached_teacher_count',
        'stats_last_synced',
    ]
    actions = [
        'action_approve',
        'action_suspend',
        'action_activate',
        'action_enable_mobile',
        'action_disable_mobile',
    ]
    fieldsets = (
        ('School Information', {
            'fields': ('name', 'schema_name', 'created_on', 'onboarding_completed'),
        }),
        ('Status', {
            'fields': ('status',),
            'description': 'Use the actions menu to bulk-change status. '
                           'Direct edits here bypass email notifications.',
        }),
        ('Mobile App Access', {
            'fields': ('has_mobile_access', 'mobile_access_granted'),
            'description': 'Enable/disable mobile app access (Premium feature).',
        }),
        ('Contact Information', {
            'fields': ('contact_email', 'contact_phone'),
            'classes': ('collapse',),
        }),
        ('Branding', {
            'fields': ('logo', 'primary_color', 'website', 'address'),
            'classes': ('collapse',),
        }),
        ('Cached Stats', {
            'fields': ('cached_student_count', 'cached_teacher_count', 'stats_last_synced'),
            'classes': ('collapse',),
            'description': 'Refreshed automatically every 30 min via Celery Beat.',
        }),
    )

    def save_model(self, request, obj, form, change):
        is_new = obj.pk is None
        super().save_model(request, obj, form, change)
        
        if is_new:
            from .models import Domain
            from django.conf import settings
            from .tasks import provision_tenant_task
            from django.contrib import messages
            
            # 1. Ensure Domain exists
            full_domain = f"{obj.schema_name}.{settings.BASE_DOMAIN}"
            Domain.objects.get_or_create(
                domain=full_domain,
                tenant=obj,
                defaults={'is_primary': True}
            )
            
            # 2. Set default admin info if not provided
            update_fields = ['status']
            if not obj.pending_admin_email:
                obj.pending_admin_email = f"admin@{full_domain}"
                obj.pending_admin_first_name = "Admin"
                obj.pending_admin_last_name = "User"
                update_fields.extend(['pending_admin_email', 'pending_admin_first_name', 'pending_admin_last_name'])
                
            # 3. Transition to provisioning state and queue task
            obj.status = TenantStatus.PROVISIONING
            obj.save(update_fields=update_fields)
            
            provision_tenant_task.delay(obj.id, request.user.id)
            messages.info(request, f"Background provisioning started for {obj.name} (Celery task queued).")

    # ─── Display helpers ───────────────────────────────────────────────────────

    @admin.display(description='Plan')
    def plan_badge(self, obj):
        if obj.has_mobile_access:
            return '⭐ Premium'
        return '💻 Standard'

    @admin.display(description='Status')
    def status_badge(self, obj):
        colours = {
            TenantStatus.ACTIVE:    ('green',  '✅'),
            TenantStatus.PENDING:   ('orange', '⏳'),
            TenantStatus.SUSPENDED: ('red',    '🚫'),
            TenantStatus.REJECTED:  ('grey',   '✗'),
        }
        colour, icon = colours.get(obj.status, ('grey', '?'))
        return format_html(
            '<span style="color:{}">{} {}</span>',
            colour,
            icon,
            obj.get_status_display(),
        )

    @admin.display(description='Domain')
    def primary_domain(self, obj):
        domain = obj.domains.filter(is_primary=True).first()
        if domain:
            return format_html(
                '<a href="https://{}" target="_blank">🌐 {}</a>',
                domain.domain,
                domain.domain,
            )
        return '—'

    # ─── Bulk actions ──────────────────────────────────────────────────────────

    @admin.action(description='✅ Approve selected schools')
    def action_approve(self, request, queryset):
        # Only approve pending schools — skip others silently
        eligible = queryset.filter(status=TenantStatus.PENDING)
        count    = 0
        for tenant in eligible:
            tenant.status = TenantStatus.ACTIVE
            tenant.save()
            count += 1
        skipped = queryset.count() - count
        msg = f'{count} school(s) approved.'
        if skipped:
            msg += f' {skipped} skipped (not pending).'
        self.message_user(request, msg)

    @admin.action(description='🚫 Suspend selected schools')
    def action_suspend(self, request, queryset):
        # Only suspend active schools
        eligible = queryset.filter(status=TenantStatus.ACTIVE)
        count    = eligible.count()
        # Use update() for bulk but also set suspension_reason to indicate admin action
        eligible.update(
            status=TenantStatus.SUSPENDED,
            suspension_reason='Suspended via Django admin bulk action',
        )
        skipped = queryset.count() - count
        msg = f'{count} school(s) suspended.'
        if skipped:
            msg += f' {skipped} skipped (not active).'
        self.message_user(request, msg)

    @admin.action(description='▶️ Reactivate selected schools')
    def action_activate(self, request, queryset):
        eligible = queryset.filter(status=TenantStatus.SUSPENDED)
        count    = eligible.count()
        eligible.update(status=TenantStatus.ACTIVE, suspension_reason=None)
        skipped  = queryset.count() - count
        msg = f'{count} school(s) reactivated.'
        if skipped:
            msg += f' {skipped} skipped (not suspended).'
        self.message_user(request, msg)

    @admin.action(description='⭐ Enable mobile app access')
    def action_enable_mobile(self, request, queryset):
        count = 0
        for tenant in queryset:
            tenant.enable_mobile_access()  # uses model method — sets date correctly
            count += 1
        self.message_user(request, f'Mobile access enabled for {count} school(s).')

    @admin.action(description='💻 Disable mobile app access')
    def action_disable_mobile(self, request, queryset):
        count = 0
        for tenant in queryset:
            tenant.disable_mobile_access()
            count += 1
        self.message_user(request, f'Mobile access disabled for {count} school(s).')


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display  = ['domain', 'tenant', 'is_primary', 'tenant_status', 'tenant_plan']
    list_filter   = ['is_primary', 'tenant__status']
    search_fields = ['domain', 'tenant__name']
    readonly_fields = ['domain', 'tenant']  # domains shouldn't be edited directly

    @admin.display(description='Tenant status')
    def tenant_status(self, obj):
        return obj.tenant.get_status_display()

    @admin.display(description='Plan')
    def tenant_plan(self, obj):
        return obj.tenant.get_plan_name()