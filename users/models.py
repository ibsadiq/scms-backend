from django.db import models
from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.contrib.auth.models import Group
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from administration.common_objs import *
from .managers import CustomUserManager
from .invitation_models import UserInvitation


class CustomUser(AbstractBaseUser, PermissionsMixin):
    first_name = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="first name"
    )
    middle_name = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="middle name"
    )
    last_name = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="last name"
    )
    phone_number = models.CharField(max_length=15, unique=True, blank=True, null=True)
    email = models.EmailField(_("email address"), unique=True)
    date_joined = models.DateTimeField(default=timezone.now)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_admin = models.BooleanField(default=False, help_text="School-level administrator")
    is_accountant = models.BooleanField(default=False)
    is_teacher = models.BooleanField(default=False)
    is_parent = models.BooleanField(default=False)
    is_student = models.BooleanField(default=False)
    is_inspector = models.BooleanField(
        default=False, 
        help_text="Public-schema only. Cross-tenant read-only access. "
          "Not part of school-level active_role switching.")
    active_role = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        choices=[
            ('admin', 'Admin'),
            ('teacher', 'Teacher'),
            ('parent', 'Parent'),
            ('student', 'Student'),
            ('accountant', 'Accountant'),
            ('staff', 'Staff'),
        ],
        help_text="Currently active role for users with multiple roles"
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    class Meta:
        ordering = ["email"]

    def __str__(self):
        return self.email

    def get_full_name(self):
        """Return the full name of the user"""
        if self.first_name or self.last_name:
            return f"{self.first_name} {self.last_name}".strip()
        return self.email

    def get_available_roles(self):
        """Return list of roles available to this user"""
        roles = []
        if self.is_admin:
            roles.append('admin')
        if self.is_teacher:
            roles.append('teacher')
        if self.is_parent:
            roles.append('parent')
        if self.is_student:
            roles.append('student')
        if self.is_accountant:
            roles.append('accountant')
        if not roles and self.has_ordinary_staff_identity():
            roles.append('staff')
        return roles

    def has_ordinary_staff_identity(self):
        """Return whether this user is an active, non-specialist tenant staff member."""
        from django.db import connection
        from django_tenants.utils import get_public_schema_name

        if not self.pk or any((
            self.is_admin,
            self.is_teacher,
            self.is_accountant,
            self.is_parent,
            self.is_student,
        )):
            return False

        # Staff identities are tenant-local. The academic Staff table is not
        # part of the public schema and platform users must never resolve to a
        # tenant staff role.
        if connection.schema_name == get_public_schema_name():
            return False

        from academic.models import Staff

        return Staff.objects.filter(
            user_id=self.pk,
            is_active=True,
            role=Staff.Role.OTHER,
        ).exists()

    def get_effective_role(self):
        """Resolve the current role without granting authority from Django is_staff."""
        available_roles = self.get_available_roles()
        if self.active_role in available_roles:
            return self.active_role
        return available_roles[0] if available_roles else None

    def ensure_active_role(self):
        """Persist a valid default role when the stored selection is absent or stale."""
        effective_role = self.get_effective_role()
        if effective_role != self.active_role:
            self.active_role = effective_role
            self.save(update_fields=['active_role'])
        return effective_role

    def set_active_role(self, role):
        """Set the active role for this user"""
        available_roles = self.get_available_roles()
        if role not in available_roles:
            raise ValueError(f"User does not have role: {role}")
        self.active_role = role
        self.save(update_fields=['active_role'])
