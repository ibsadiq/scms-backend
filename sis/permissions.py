from rest_framework.permissions import BasePermission, SAFE_METHODS

from academic.services.academic_authority_service import AcademicAuthorityService
from .access import can_read_sis_students


class SISStudentPermission(BasePermission):
    """Role boundary for general and related SIS student endpoints."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return can_read_sis_students(request.user)
        return AcademicAuthorityService.is_school_admin(request.user)
