from rest_framework.permissions import BasePermission

from academic.services.academic_authority_service import AcademicAuthorityService


class CanViewBackgroundJob(BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.created_by_id == request.user.id or AcademicAuthorityService.is_school_admin(
            request.user
        )
