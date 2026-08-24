from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from academic.models import (
    Teacher,
    Department,
    AcademicLeadershipRole,
    AcademicLeadershipAssignment,
    SectionType,
)
from administration.models import AcademicYear


class AcademicLeadershipService:
    """
    Manages assignment and deactivation of academic leadership roles (HOD, Head Teacher).
    """

    @classmethod
    def _verify_admin(cls, actor):
        if actor is not None:
            is_admin = (
                getattr(actor, "is_admin", False)
                or getattr(actor, "is_staff", False)
                or getattr(actor, "is_superuser", False)
            )
            if not is_admin:
                raise PermissionDenied("Only school administrators can assign academic leadership roles.")

    @classmethod
    @transaction.atomic
    def assign_hod(
        cls,
        *,
        teacher: Teacher,
        department: Department,
        academic_year: AcademicYear,
        actor=None,
    ) -> AcademicLeadershipAssignment:
        """
        Assigns a Teacher as Head of Department for a specified academic year.
        Deactivates any existing active HOD for the same department and academic year.
        """
        cls._verify_admin(actor)

        # Deactivate existing active HOD for this department + year
        AcademicLeadershipAssignment.objects.filter(
            department=department,
            academic_year=academic_year,
            role=AcademicLeadershipRole.HOD,
            is_active=True,
        ).update(is_active=False)

        assignment = AcademicLeadershipAssignment(
            teacher=teacher,
            role=AcademicLeadershipRole.HOD,
            department=department,
            section=None,
            academic_year=academic_year,
            is_active=True,
        )
        assignment.full_clean()
        assignment.save()
        return assignment

    @classmethod
    @transaction.atomic
    def assign_head_teacher(
        cls,
        *,
        teacher: Teacher,
        section: str,
        academic_year: AcademicYear,
        actor=None,
    ) -> AcademicLeadershipAssignment:
        """
        Assigns a Teacher as Head Teacher for a specified school section and academic year.
        Deactivates any existing active Head Teacher for the same section and academic year.
        """
        cls._verify_admin(actor)

        if section not in SectionType.values:
            raise ValidationError(f"Invalid section type: {section}")

        AcademicLeadershipAssignment.objects.filter(
            section=section,
            academic_year=academic_year,
            role=AcademicLeadershipRole.HEAD_TEACHER,
            is_active=True,
        ).update(is_active=False)

        assignment = AcademicLeadershipAssignment(
            teacher=teacher,
            role=AcademicLeadershipRole.HEAD_TEACHER,
            department=None,
            section=section,
            academic_year=academic_year,
            is_active=True,
        )
        assignment.full_clean()
        assignment.save()
        return assignment

    @classmethod
    def deactivate_assignment(
        cls,
        *,
        assignment_id: int,
        actor=None,
    ) -> AcademicLeadershipAssignment:
        cls._verify_admin(actor)
        assignment = AcademicLeadershipAssignment.objects.get(pk=assignment_id)
        assignment.is_active = False
        assignment.save(update_fields=["is_active", "updated_at"])
        return assignment

    @classmethod
    def get_active_hod(
        cls,
        *,
        department: Department,
        academic_year: AcademicYear,
    ):
        return AcademicLeadershipAssignment.objects.filter(
            department=department,
            academic_year=academic_year,
            role=AcademicLeadershipRole.HOD,
            is_active=True,
        ).first()

    @classmethod
    def get_active_head_teacher(
        cls,
        *,
        section: str,
        academic_year: AcademicYear,
    ):
        return AcademicLeadershipAssignment.objects.filter(
            section=section,
            academic_year=academic_year,
            role=AcademicLeadershipRole.HEAD_TEACHER,
            is_active=True,
        ).first()
