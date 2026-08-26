from django.db import transaction

from academic.models import Staff, Teacher


class StaffIdentityService:
    """Creates or links a single general Staff identity without replacing role profiles."""

    @staticmethod
    def role_for_user(user):
        if getattr(user, "is_teacher", False):
            return Staff.Role.TEACHER
        if getattr(user, "is_admin", False):
            return Staff.Role.ADMINISTRATOR
        if getattr(user, "is_accountant", False):
            return Staff.Role.ACCOUNTANT
        return Staff.Role.OTHER

    @classmethod
    @transaction.atomic
    def ensure_for_user(cls, user, **defaults):
        values = {"role": cls.role_for_user(user), **defaults}
        staff, created = Staff.objects.get_or_create(user=user, defaults=values)
        return staff, created

    @classmethod
    @transaction.atomic
    def ensure_for_teacher(cls, teacher: Teacher):
        if teacher.staff_id:
            return teacher.staff, False

        defaults = {
            "role": Staff.Role.TEACHER,
            "designation": "Teacher",
            "image": teacher.image,
        }
        staff, created = cls.ensure_for_user(teacher.user, **defaults)

        changed = []
        if staff.role != Staff.Role.TEACHER:
            staff.role = Staff.Role.TEACHER
            changed.append("role")
        if not staff.image and teacher.image:
            staff.image = teacher.image
            changed.append("image")
        if changed:
            staff.save(update_fields=[*changed, "updated_at"])

        teacher.staff = staff
        teacher.save(update_fields=["staff"])
        return staff, created
