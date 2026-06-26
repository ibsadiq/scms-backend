# tenants/models.py
from django.db import models
from django_tenants.models import TenantMixin, DomainMixin
from django_tenants.utils import schema_context
from django.contrib.auth import get_user_model
from django.conf import settings

import environ
env = environ.Env()


class TenantStatus(models.TextChoices):
    PENDING   = 'pending',   'Pending Approval'
    ACTIVE    = 'active',    'Active'
    SUSPENDED = 'suspended', 'Suspended'
    REJECTED  = 'rejected',  'Rejected'



class Client(TenantMixin):

    cached_student_count = models.PositiveIntegerField(default=0)
    cached_teacher_count = models.PositiveIntegerField(default=0)
    stats_last_synced    = models.DateTimeField(null=True, blank=True)

    
    name = models.CharField(max_length=100)
    created_on = models.DateField(auto_now_add=True)

    status = models.CharField(
        max_length=20,
        choices=TenantStatus.choices,
        default=TenantStatus.PENDING,
        db_index=True,
        help_text="Current lifecycle state of the tenant"
    )
    
    # The ONLY premium feature - mobile app access
    has_mobile_access = models.BooleanField(
        default=False,
        help_text="Enable mobile app access (iOS/Android apps)"
    )
    
    # Optional: Contact info
    contact_email = models.EmailField(blank=True, null=True, unique=True)
    contact_phone = models.CharField(max_length=20, blank=True, null=True)

    logo = models.ImageField(
        upload_to='tenant_logos/',
        blank=True,
        null=True,
        help_text="School logo (appears in emails and portal)"
    )
    primary_color = models.CharField(
        max_length=7,
        default='#047857',
        help_text="Primary brand color (hex code)"
    )
    website = models.URLField(
        blank=True,
        null=True,
        help_text="School website URL"
    )
    address = models.TextField(
        blank=True,
        null=True,
        help_text="School physical address"
    )
    approved_at   = models.DateTimeField(null=True, blank=True)
    suspended_at  = models.DateTimeField(null=True, blank=True)
    rejected_at   = models.DateTimeField(null=True, blank=True)

    # Who did it
    approved_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='approved_tenants'
    )
    suspended_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='suspended_tenants'
    )

    # Reason log
    suspension_reason = models.TextField(blank=True, null=True)
    rejection_reason  = models.TextField(blank=True, null=True)

    
    # Optional: Track when mobile access was granted
    mobile_access_granted = models.DateField(blank=True, null=True)

    onboarding_completed = models.BooleanField(
        default=False,
        help_text="True once the school admin has completed (or skipped) the first-run setup wizard"
    )

    auto_create_schema = True
    
    def __str__(self):
        return self.name
    
    @property
    def is_active(self):
        return self.status == TenantStatus.ACTIVE
    
    def get_plan_name(self):
        """Simple plan name"""
        return "Premium (Web + Mobile)" if self.has_mobile_access else "Standard (Web Only)"
    
    def enable_mobile_access(self):
        """Grant mobile app access"""
        from datetime import date
        self.has_mobile_access = True
        if not self.mobile_access_granted:
            self.mobile_access_granted = date.today()
        self.save()
    
    def disable_mobile_access(self):
        """Revoke mobile app access"""
        self.has_mobile_access = False
        self.save()

    def get_logo_url(self):
        """Get full URL for logo"""
        if self.logo:
            from django.conf import settings
            logo_url = self.logo.url
            # Cloud storage (S3/Cloudinary/Spaces/etc.) — url is already absolute
            if logo_url.startswith('http://') or logo_url.startswith('https://'):
                return logo_url
            # Local dev — prepend backend host
            base_url = getattr(settings, 'BACKEND_URL', 'http://localhost:8000').rstrip('/')
            return f"{base_url}{logo_url}"
        return None
    
    def get_website_url(self):
        """Get website URL or primary domain"""
        if self.website:
            return self.website
        
        # Fallback to primary domain
        domain = self.domains.filter(is_primary=True).first()
        if domain:
            return f"https://{domain.domain}"
        return None
    
    def get_usage_stats(self):
        """Get current usage statistics"""
        from django_tenants.utils import schema_context
        
        try:
            with schema_context(self.schema_name):
                from academic.models import Student, Teacher
                
                return {
                    'total_students': Student.objects.filter(status='Active').count(),
                    'total_teachers': Teacher.objects.count(),
                }
        except:
            return {'total_students': 0, 'total_teachers': 0}
    
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        
        if self.contact_email:
            self.contact_email = self.contact_email.lower()
            
        super().save(*args, **kwargs)
        
        # Only run for new tenants (not the 'public' tenant)
        if is_new and self.schema_name != 'public':
            self._setup_new_tenant()

    def _setup_new_tenant(self):
        """Internal helper to provision a new tenant's initial data"""
        from django_tenants.utils import schema_context
        from django.contrib.auth import get_user_model
        import logging

        logger = logging.getLogger(__name__)

        try:
            with schema_context(self.schema_name):
                User = get_user_model()
                support_email = 'support@ssync.online'
                
                if not User.objects.filter(email=support_email).exists():
                    User.objects.create_superuser(
                        email=env('TENANT_ADMIN_EMAIL', default=support_email),
                        password=env('TENANT_ADMIN_PASSWORD', default='ChangeMe123!'), 
                        phone_number='+00000000000',
                        first_name='SSync',
                        last_name='Support',
                        is_active=True
                    )
        except Exception as e:
            logger.error(f"Failed to provision tenant {self.schema_name}: {str(e)}")                

class Domain(DomainMixin):
    pass



class Inspector(models.Model):
    """
    A public official (e.g. Ministry officer) who can view school data
    without management permissions.

    Relationship:
        Inspector  ──(OneToOne)──►  CustomUser   (login credentials)
        Inspector  ──(M2M)───────►  Client[]     (assigned schools)

    Access levels:
        global   → sees ALL active schools
        assigned → sees only schools in assigned_tenants
    """

    class AccessLevel(models.TextChoices):
        GLOBAL   = 'global',   'All Schools'
        ASSIGNED = 'assigned', 'Assigned Schools'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='inspector_profile',
        help_text='Login account for this inspector',
    )
    title = models.CharField(
        max_length=100,
        blank=True,
        help_text='e.g. "Senior Education Officer"',
    )
    organisation = models.CharField(
        max_length=150,
        blank=True,
        help_text='e.g. "Federal Ministry of Education"',
    )
    access_level = models.CharField(
        max_length=20,
        choices=AccessLevel.choices,
        default=AccessLevel.ASSIGNED,
    )
    assigned_tenants = models.ManyToManyField(
        'tenants.Client',
        blank=True,
        related_name='inspectors',
        help_text='Visible schools — only applies when access_level = assigned',
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(
        blank=True,
        help_text='Internal admin notes',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['user__email']

    def __str__(self):
        return f"{self.user.email} [{self.get_access_level_display()}]"

    def get_visible_tenants(self):
        """
        Returns the queryset of Client tenants this inspector can see.
        Always limited to active schools only.
        """
        from tenants.models import Client, TenantStatus

        base = Client.objects.exclude(schema_name='public').filter(
            status=TenantStatus.ACTIVE
        )
        if self.access_level == self.AccessLevel.GLOBAL:
            return base
        return base.filter(pk__in=self.assigned_tenants.values_list('pk', flat=True))