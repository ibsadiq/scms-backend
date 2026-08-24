from django.db.models import Q

from academic.models import AllocatedSubject, Student
from academic.services.academic_authority_service import AcademicAuthorityService
from attendance.permissions import teacher_classroom_ids
from users.models import CustomUser


class MessagingPolicy:
    @staticmethod
    def is_admin(user):
        return bool(
            user and user.is_authenticated
            and AcademicAuthorityService.is_school_admin(user)
        )

    @classmethod
    def admin_queryset(cls):
        return CustomUser.objects.filter(
            Q(is_admin=True) | Q(is_superuser=True), is_active=True,
        ).distinct()

    @staticmethod
    def linked_students(user):
        if getattr(user, "is_parent", False) and getattr(user, "parent", None):
            return Student.objects.filter(parent_guardian=user.parent, is_active=True)
        if getattr(user, "is_student", False):
            return Student.objects.filter(user=user, is_active=True)
        return Student.objects.none()

    @staticmethod
    def teacher_students(user):
        if not getattr(user, "teacher", None):
            return Student.objects.none()
        return Student.objects.filter(
            classroom_id__in=teacher_classroom_ids(user), is_active=True,
        )

    @staticmethod
    def teachers_for_students(students):
        classroom_ids = students.exclude(classroom_id=None).values("classroom_id")
        teacher_ids = AllocatedSubject.objects.filter(
            class_room_id__in=classroom_ids,
        ).values("teacher_name_id")
        return CustomUser.objects.filter(
            Q(teacher__classroom__id__in=classroom_ids)
            | Q(teacher__id__in=teacher_ids),
            is_active=True,
        ).distinct()

    @classmethod
    def allowed_recipient_queryset(cls, sender):
        if cls.is_admin(sender):
            return CustomUser.objects.filter(is_active=True).exclude(pk=sender.pk)
        admins = cls.admin_queryset().exclude(pk=sender.pk)
        if getattr(sender, "teacher", None):
            students = cls.teacher_students(sender)
            family_users = CustomUser.objects.filter(
                Q(student_profile__in=students)
                | Q(parent__children__in=students),
                is_active=True,
            )
            return CustomUser.objects.filter(
                Q(pk__in=admins.values("pk"))
                | Q(pk__in=family_users.values("pk")),
                is_active=True,
            ).exclude(pk=sender.pk).distinct()
        if getattr(sender, "is_parent", False) or getattr(sender, "is_student", False):
            teachers = cls.teachers_for_students(cls.linked_students(sender))
            return CustomUser.objects.filter(
                Q(pk__in=admins.values("pk"))
                | Q(pk__in=teachers.values("pk")),
                is_active=True,
            ).exclude(pk=sender.pk).distinct()
        return admins.distinct()

    @classmethod
    def can_sender_contact_recipient(cls, sender, recipient, student=None):
        if not recipient or not cls.allowed_recipient_queryset(sender).filter(pk=recipient.pk).exists():
            return False
        if student is None:
            return True
        if cls.is_admin(sender):
            return Student.objects.filter(pk=student.pk).exists()
        if getattr(sender, "teacher", None):
            if not cls.teacher_students(sender).filter(pk=student.pk).exists():
                return False
            if getattr(recipient, "is_parent", False):
                return bool(getattr(recipient, "parent", None)) and student.parent_guardian_id == recipient.parent.pk
            if getattr(recipient, "is_student", False):
                return student.user_id == recipient.pk
            return cls.is_admin(recipient)
        if getattr(sender, "is_parent", False):
            if not cls.linked_students(sender).filter(pk=student.pk).exists():
                return False
            return cls.is_admin(recipient) or cls.teachers_for_students(
                Student.objects.filter(pk=student.pk)
            ).filter(pk=recipient.pk).exists()
        if getattr(sender, "is_student", False):
            if student.user_id != sender.pk:
                return False
            return cls.is_admin(recipient) or cls.teachers_for_students(
                Student.objects.filter(pk=student.pk)
            ).filter(pk=recipient.pk).exists()
        return False

    @staticmethod
    def can_access_thread(user, message):
        return user.pk in {message.sender_id, message.recipient_id}

    @classmethod
    def classroom_family_students(cls, user, classroom_id=None):
        if cls.is_admin(user):
            students = Student.objects.filter(is_active=True)
        elif getattr(user, "teacher", None):
            students = cls.teacher_students(user)
        else:
            return Student.objects.none()
        if classroom_id:
            students = students.filter(classroom_id=classroom_id)
        return students.select_related(
            "parent_guardian__user", "classroom__name"
        ).order_by("classroom_id", "last_name", "first_name")
