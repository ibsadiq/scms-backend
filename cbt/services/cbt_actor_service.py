from django.core.exceptions import ValidationError, ObjectDoesNotExist

from academic.models import Teacher


class CBTActorService:
    """
    Service for validating and resolving CBT actor identities (e.g. Teachers and Students).
    """

    @staticmethod
    def resolve_teacher(actor):
        """
        Resolves an actor (Teacher or CustomUser) to a valid Teacher instance.
        Raises ValidationError if actor is null or does not have a Teacher profile.
        """
        if actor is None:
            raise ValidationError("A valid teacher or user actor is required.")

        if isinstance(actor, Teacher):
            return actor

        # 1. Try reverse relation catching ObjectDoesNotExist
        try:
            teacher = getattr(actor, "teacher", None)
            if teacher:
                return teacher
        except (ObjectDoesNotExist, Exception):
            pass

        # 2. Query Teacher in current tenant schema by user_id
        if hasattr(actor, "pk") and actor.pk:
            try:
                teacher = Teacher.objects.filter(user_id=actor.pk).first()
                if teacher:
                    return teacher
            except Exception:
                pass

        raise ValidationError(
            f"The user '{getattr(actor, 'email', str(actor))}' does not have an associated Teacher profile."
        )

    @staticmethod
    def resolve_student(actor):
        """
        Resolves an actor (Student or CustomUser) to a valid Student instance.
        Raises ValidationError if actor is null or does not have a Student profile.
        """
        if actor is None:
            raise ValidationError("A valid student or user actor is required.")

        from academic.models import Student

        if isinstance(actor, Student):
            return actor

        # 1. Try reverse relation catching ObjectDoesNotExist
        try:
            student = getattr(actor, "student_profile", None)
            if student:
                return student
        except (ObjectDoesNotExist, Exception):
            pass

        # 2. Query Student in current tenant schema by user_id
        if hasattr(actor, "pk") and actor.pk:
            try:
                student = Student.objects.filter(user_id=actor.pk).first()
                if student:
                    return student
            except Exception:
                pass

        raise ValidationError(
            f"The user '{getattr(actor, 'email', str(actor))}' does not have an associated Student profile."
        )
