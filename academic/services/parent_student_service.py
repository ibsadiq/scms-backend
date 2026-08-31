from django.core.exceptions import ValidationError
from django.db import transaction

from academic.models import Student


class ParentStudentService:
    @classmethod
    @transaction.atomic
    def sync_students(cls, parent, student_ids):
        ids = list(dict.fromkeys(student_ids))
        students = list(Student.objects.select_for_update().filter(pk__in=ids))
        found = {student.pk for student in students}
        missing = [pk for pk in ids if pk not in found]
        if missing:
            raise ValidationError(f"Student(s) not found: {missing}")
        Student.objects.select_for_update().filter(parent_guardian=parent).exclude(pk__in=ids).update(parent_guardian=None, parent_contact=None)
        if ids:
            Student.objects.filter(pk__in=ids).update(parent_guardian=parent, parent_contact=parent.phone_number)

    @staticmethod
    @transaction.atomic
    def synchronize_contact(parent):
        Student.objects.select_for_update().filter(parent_guardian=parent).update(parent_contact=parent.phone_number)

    @staticmethod
    @transaction.atomic
    def assign_parent(student, parent):
        student = Student.objects.select_for_update().get(pk=student.pk)
        student.parent_guardian = parent
        student.parent_contact = parent.phone_number if parent else None
        student.save(update_fields=["parent_guardian", "parent_contact"])
        return student

    @staticmethod
    @transaction.atomic
    def detach_all(parent):
        Student.objects.select_for_update().filter(parent_guardian=parent).update(parent_guardian=None, parent_contact=None)
