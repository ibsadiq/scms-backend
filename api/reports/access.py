from academic.models import Student
from attendance.permissions import teacher_classroom_ids

from .permissions import is_school_admin


class ReportAccessService:
    @staticmethod
    def administrative_students(user):
        if not is_school_admin(user):
            return Student.objects.none()
        return Student.objects.all()

    @staticmethod
    def finance_students(user):
        if not (
            is_school_admin(user) or getattr(user, "is_accountant", False)
        ):
            return Student.objects.none()
        return Student.objects.all()

    @staticmethod
    def academic_students(user):
        if is_school_admin(user):
            return Student.objects.all()
        if not getattr(user, "teacher", None):
            return Student.objects.none()
        return Student.objects.filter(
            classroom_id__in=teacher_classroom_ids(user)
        )

    @staticmethod
    def attendance_classroom_ids(user):
        if is_school_admin(user):
            return None
        if getattr(user, "teacher", None):
            return teacher_classroom_ids(user)
        return []
