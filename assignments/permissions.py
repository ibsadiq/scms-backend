"""
Permissions for assignments app
"""
from rest_framework import permissions
from academic.models import Teacher


class IsTeacher(permissions.BasePermission):
    """
    Permission to check if user is a teacher, admin, or staff
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return (
            hasattr(request.user, 'teacher') or
            getattr(request.user, 'is_admin', False) or
            getattr(request.user, 'is_staff', False) or
            getattr(request.user, 'is_superuser', False)
        )
