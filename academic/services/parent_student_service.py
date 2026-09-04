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

    @classmethod
    @transaction.atomic
    def delete_parent(cls, parent):
        """
        Canonical atomic parent deletion lifecycle:
        1. Lock parent and resolve linked CustomUser.
        2. Detach all linked students (clearing parent_guardian and parent_contact).
        3. Invalidate pending parent invitations.
        4. Decouple/update linked CustomUser (never hard-deleting the user):
           - Clear is_parent = False
           - Remove from 'parent' Group
           - Recalculate active_role
           - If user has another legitimate active role, keep is_active = True
           - If user has no other role, set is_active = False
        5. Delete Parent record.
        """
        from django.contrib.auth.models import Group
        from users.models import UserInvitation, CustomUser

        if not parent or not parent.pk:
            return

        parent = parent.__class__.objects.select_for_update().filter(pk=parent.pk).first()
        if not parent:
            return

        user = parent.user
        if user:
            user = CustomUser.objects.select_for_update().filter(pk=user.pk).first()

        # 2. Detach all students
        cls.detach_all(parent)

        # 3. Invalidate pending parent invitations unambiguously belonging to this parent
        UserInvitation.objects.filter(
            parent_profile_id=parent.pk,
            role="parent",
            status="pending",
        ).update(status="expired")

        if parent.email:
            UserInvitation.objects.filter(
                email__iexact=parent.email.strip(),
                role="parent",
                status="pending",
                parent_profile_id__in=[parent.pk, None],
            ).update(status="expired")

        # 4. Handle linked CustomUser
        if user:
            user.is_parent = False
            group = Group.objects.filter(name="parent").first()
            if group:
                user.groups.remove(group)

            remaining_roles = user.get_available_roles()
            has_other_role = bool(
                remaining_roles
                or user.is_staff
                or user.is_superuser
                or getattr(user, "is_inspector", False)
            )

            update_fields = ["is_parent"]

            if has_other_role:
                user.is_active = True
                update_fields.append("is_active")
                if user.active_role == "parent":
                    user.active_role = user.get_effective_role()
                    update_fields.append("active_role")
            else:
                user.is_active = False
                user.active_role = None
                update_fields.extend(["is_active", "active_role"])

            user.save(update_fields=update_fields)

        # 5. Delete Parent row
        parent.delete()

