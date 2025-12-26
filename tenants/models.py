from django.db import models
from django.conf import settings
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError


class OnboardingStep(models.IntegerChoices):
    SCHOOL_INFO = 1, "School Information"
    ADMIN = 2, "Admin Account"
    BRANDING = 3, "Branding"
    COMPLETED = 4, "Completed"


class SchoolSettings(models.Model):
    """
    Single school settings and configuration.
    Only one instance should exist (enforced in save method).
    Combines both onboarding and academic settings in one place.
    """
    # Basic school info
    school_name = models.CharField(max_length=255)
    logo = models.ImageField(upload_to="school_logos/", blank=True, null=True)

    # Branding
    primary_color = models.CharField(max_length=20, default="#047857")
    secondary_color = models.CharField(max_length=20, blank=True, null=True)

    # Contact info
    address = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    contact_phone = models.CharField(max_length=20, blank=True, null=True)
    contact_email = models.EmailField(blank=True, null=True)
    website = models.URLField(blank=True, null=True, validators=[URLValidator()])

    # Academic settings (filled in after onboarding)
    academic_year_start_month = models.IntegerField(
        default=9,
        choices=[(i, f'{i}') for i in range(1, 13)],
        help_text='Month when academic year starts (1=January, 12=December)',
        blank=True, null=True
    )
    terms_per_year = models.IntegerField(
        default=3,
        choices=[(2, '2 Terms'), (3, '3 Terms'), (4, '4 Terms (Quarters)')],
        help_text='Number of terms per academic year',
        blank=True, null=True
    )

    # Onboarding fields
    onboarding_step = models.PositiveSmallIntegerField(
        choices=OnboardingStep.choices,
        default=OnboardingStep.SCHOOL_INFO,
        help_text="Current onboarding step"
    )

    onboarding_completed = models.BooleanField(
        default=False,
        help_text="Whether the initial setup wizard has been completed"
    )

    admin_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="school_admin",
        help_text="The primary admin user created during onboarding"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "School Settings"
        verbose_name_plural = "School Settings"

    def __str__(self):
        return self.school_name

    def save(self, *args, **kwargs):
        """Ensure only one SchoolSettings instance exists"""
        if not self.pk and SchoolSettings.objects.exists():
            # Update existing instance instead of creating new one
            existing = SchoolSettings.objects.first()
            self.pk = existing.pk
        super().save(*args, **kwargs)

    @classmethod
    def get_settings(cls):
        """Get or create the single school settings instance"""
        settings, _ = cls.objects.get_or_create(
            pk=1,
            defaults={'school_name': 'My School'}
        )
        return settings

    @property
    def needs_onboarding(self):
        return not self.onboarding_completed

    def can_advance_to(self, step: OnboardingStep) -> bool:
        return step == self.onboarding_step

    def advance_onboarding(self, next_step: OnboardingStep):
        self.onboarding_step = next_step
        self.save(update_fields=["onboarding_step"])

    def complete_onboarding(self):
        self.onboarding_step = OnboardingStep.COMPLETED
        self.onboarding_completed = True
        self.save(update_fields=["onboarding_step", "onboarding_completed"])

    def clean(self):
        """Validate hex color format"""
        if self.primary_color:
            if not self.primary_color.startswith('#'):
                raise ValidationError({'primary_color': 'Color must start with #'})
            if len(self.primary_color) not in [4, 7]:  # #RGB or #RRGGBB
                raise ValidationError({'primary_color': 'Invalid hex color format'})


# Keep Tenant as alias for backward compatibility
Tenant = SchoolSettings
