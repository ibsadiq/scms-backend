from academic.models import Student
from academic.services.academic_authority_service import AcademicAuthorityService
from attendance.permissions import teacher_classroom_ids


def student_queryset_for_user(user, queryset=None):
    """Return the tenant-local Student queryset the actor may read."""
    queryset = queryset if queryset is not None else Student.objects.all()
    if not user or not user.is_authenticated:
        return queryset.none()
    if AcademicAuthorityService.is_school_admin(user):
        return queryset

    teacher = getattr(user, "teacher", None)
    if teacher:
        return queryset.filter(classroom_id__in=teacher_classroom_ids(user))

    parent = getattr(user, "parent", None)
    if getattr(user, "is_parent", False) and parent:
        return queryset.filter(parent_guardian=parent)

    if getattr(user, "is_student", False):
        return queryset.filter(user=user)

    if getattr(user, "is_accountant", False):
        return queryset.filter(is_active=True)

    return queryset.none()


def can_read_sis_students(user):
    if not user or not user.is_authenticated:
        return False
    return bool(
        AcademicAuthorityService.is_school_admin(user)
        or getattr(user, "teacher", None)
        or (getattr(user, "is_parent", False) and getattr(user, "parent", None))
        or getattr(user, "is_student", False)
        or getattr(user, "is_accountant", False)
    )
