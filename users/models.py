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
        return roles

    def set_active_role(self, role):
        """Set the active role for this user"""
        available_roles = self.get_available_roles()
        if role not in available_roles:
            raise ValueError(f"User does not have role: {role}")
        self.active_role = role
        self.save(update_fields=['active_role'])
