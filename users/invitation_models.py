from django.db import models
from django.utils import timezone
from django.utils.crypto import get_random_string
import datetime


class UserInvitation(models.Model):
    """
    Model to store invitation tokens for teachers and parents
    """
    ROLE_CHOICES = [
        ('teacher', 'Teacher'),
        ('parent', 'Parent'),
        ('accountant', 'Accountant'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('expired', 'Expired'),
    ]

    email = models.EmailField()
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    token = models.CharField(max_length=64, unique=True, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Foreign keys to link to actual profile records
    teacher_profile_id = models.IntegerField(null=True, blank=True)
    parent_profile_id = models.IntegerField(null=True, blank=True)
    accountant_profile_id = models.IntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    invited_by = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        related_name='sent_invitations'
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['email']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.email} - {self.role} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = get_random_string(64)
        if not self.expires_at:
            # Token expires in 7 days by default
            self.expires_at = timezone.now() + datetime.timedelta(days=7)
        super().save(*args, **kwargs)

    def is_valid(self):
        """Check if invitation is still valid"""
        return (
            self.status == 'pending' and
            timezone.now() < self.expires_at
        )

    def mark_as_accepted(self):
        """Mark invitation as accepted"""
        self.status = 'accepted'
        self.accepted_at = timezone.now()
        self.save()

    def mark_as_expired(self):
        """Mark invitation as expired"""
        self.status = 'expired'
        self.save()

    @property
    def is_expired(self):
        """Check if invitation has expired"""
        return timezone.now() >= self.expires_at

    @property
    def days_until_expiry(self):
        """Get number of days until expiration"""
        if self.is_expired:
            return 0
        delta = self.expires_at - timezone.now()
        return delta.days
