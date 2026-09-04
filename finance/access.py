from academic.models import Student

from .permissions import is_finance_manager


def accessible_student_ids(user):
    if is_finance_manager(user):
        return Student.objects.values_list("id", flat=True)
    if getattr(user, "is_student", False):
        return Student.objects.filter(user=user).values_list("id", flat=True)
    parent = getattr(user, "parent", None)
    if getattr(user, "is_parent", False) and parent:
        from django.db.models import Q
        parent_filter = Q(parent_guardian=parent)
        if parent.phone_number:
            parent_filter |= Q(parent_contact=parent.phone_number)
        return Student.objects.filter(parent_filter).values_list("id", flat=True)
    return Student.objects.none().values_list("id", flat=True)


def can_access_student_finance(user, student):
    return bool(student and student.id in accessible_student_ids(user))
