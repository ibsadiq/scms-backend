from django.db.models import Q
from rest_framework.permissions import BasePermission, SAFE_METHODS

from academic.models import AllocatedSubject, Student
from academic.services.academic_authority_service import AcademicAuthorityService


def is_attendance_admin(user):
    return bool(user and user.is_authenticated and AcademicAuthorityService.is_school_admin(user))


def teacher_classroom_ids(user):
    teacher = getattr(user, "teacher", None)
    if not teacher:
        return []
    return list(
        AllocatedSubject.objects.filter(teacher_name=teacher)
        .values_list("class_room_id", flat=True)
        .union(
            teacher.classroom_set.values_list("id", flat=True)
        )
    )


def student_ids_for_user(user):
    if getattr(user, "is_student", False):
        return Student.objects.filter(user=user).values_list("id", flat=True)
    parent = getattr(user, "parent", None)
    if getattr(user, "is_parent", False) and parent:
        return Student.objects.filter(parent_guardian=parent).values_list("id", flat=True)
    return Student.objects.none().values_list("id", flat=True)


def can_access_classroom(user, classroom_id):
    if is_attendance_admin(user):
        return True
    return bool(getattr(user, "teacher", None)) and classroom_id in teacher_classroom_ids(user)


def can_access_student(user, student):
    if is_attendance_admin(user):
        return True
    if getattr(user, "teacher", None):
        return bool(student.classroom_id and can_access_classroom(user, student.classroom_id))
    return student.id in student_ids_for_user(user)


class AttendanceRecordPermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return bool(
                is_attendance_admin(user)
                or getattr(user, "teacher", None)
                or getattr(user, "is_student", False)
                or getattr(user, "is_parent", False)
            )
        return is_attendance_admin(user) or bool(getattr(user, "teacher", None))

    def has_object_permission(self, request, view, obj):
        if is_attendance_admin(request.user):
            return True
        if getattr(request.user, "teacher", None):
            return can_access_classroom(request.user, obj.ClassRoom_id)
        return obj.student_id in student_ids_for_user(request.user)


class CanReadAssignedAttendance(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (is_attendance_admin(request.user) or getattr(request.user, "teacher", None))
        )
