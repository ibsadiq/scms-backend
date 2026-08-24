from rest_framework.permissions import BasePermission, SAFE_METHODS

from academic.services.academic_authority_service import AcademicAuthorityService


def is_finance_manager(user):
    return bool(
        user
        and user.is_authenticated
        and (
            AcademicAuthorityService.is_school_admin(user)
            or getattr(user, "is_accountant", False)
        )
    )


class IsFinanceManager(BasePermission):
    def has_permission(self, request, view):
        return is_finance_manager(request.user)


class FinanceManagerWriteOwnRead(BasePermission):
    """Finance managers may write; students and parents receive queryset-scoped reads."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method not in SAFE_METHODS:
            return is_finance_manager(user)
        return bool(
            is_finance_manager(user)
            or getattr(user, "is_student", False)
            or getattr(user, "is_parent", False)
        )


class IsParentFinanceUser(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "is_parent", False)
            and getattr(request.user, "parent", None)
        )
