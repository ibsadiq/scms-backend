from rest_framework.permissions import BasePermission

from academic.services.academic_authority_service import AcademicAuthorityService


def is_school_admin(user):
    return bool(
        user and user.is_authenticated
        and AcademicAuthorityService.is_school_admin(user)
    )


class CanViewAdministrativeReports(BasePermission):
    def has_permission(self, request, view):
        return is_school_admin(request.user)


class CanViewFinanceReports(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated
            and (is_school_admin(user) or getattr(user, "is_accountant", False))
        )


class CanViewAttendanceReports(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated
            and (is_school_admin(user) or getattr(user, "teacher", None))
        )


class CanViewTeacherAcademicReports(CanViewAttendanceReports):
    pass
