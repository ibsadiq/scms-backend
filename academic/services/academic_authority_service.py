from django.core.exceptions import PermissionDenied
from academic.models import (
    Teacher,
    Department,
    Subject,
    AcademicLeadershipRole,
    AcademicLeadershipAssignment,
    AcademicWorkflow,
    ApprovalRoute,
)
from administration.models import AcademicYear
from .academic_approval_policy_service import AcademicApprovalPolicyService


class AcademicAuthorityService:
    """
    Centralized authority service for validating review and approval rights across academic workflows.
    Decoupled from DRF and safe against circular imports.
    """

    @classmethod
    def is_school_admin(cls, actor) -> bool:
        """
        Determines whether the actor has institutional administrative privileges.
        """
        if not actor:
            return False
        # If actor is a Teacher instance, check the underlying user
        user = getattr(actor, "user", actor)
        return bool(
            getattr(user, "is_admin", False)
            or getattr(user, "is_superuser", False)
        )

    @classmethod
    def get_teacher(cls, actor):
        """
        Resolves a Teacher instance from a CustomUser or Teacher object.
        """
        if isinstance(actor, Teacher):
            return actor
        return getattr(actor, "teacher", None)

    @classmethod
    def can_approve(
        cls,
        *,
        actor,
        workflow: str,
        subject: Subject = None,
        department: Department = None,
        section: str = None,
        academic_year: AcademicYear = None,
        creator=None,
    ) -> bool:
        """
        Evaluates whether an actor has the authority to approve an academic item.

        Rules:
        1. School Admins/Principals retain full override authority.
        2. Non-admin creators cannot approve their own work.
        3. Under ADMIN_ONLY policy, only School Admins can approve.
        4. Under ACADEMIC_LEADER_OR_ADMIN policy:
           - HOD can approve items within their department's subjects for the academic year.
           - Head Teacher can approve items within their section for the academic year.
        """
        if not actor:
            return False

        if cls.is_school_admin(actor):
            return True

        teacher = cls.get_teacher(actor)
        if not teacher:
            return False

        # Self-approval guard: non-admin creators cannot approve their own work
        if creator is not None:
            creator_teacher = cls.get_teacher(creator)
            if creator_teacher and creator_teacher.id == teacher.id:
                return False

        route = AcademicApprovalPolicyService.get_route(workflow)
        if route == ApprovalRoute.ADMIN_ONLY:
            return False

        # ACADEMIC_LEADER_OR_ADMIN routing
        # 1. HOD scope check
        target_department = department or (subject.department if subject else None)
        if target_department:
            hod_qs = AcademicLeadershipAssignment.objects.filter(
                teacher=teacher,
                role=AcademicLeadershipRole.HOD,
                department=target_department,
                is_active=True,
            )
            if academic_year:
                hod_qs = hod_qs.filter(academic_year=academic_year)
            if hod_qs.exists():
                return True

        # 2. Head Teacher scope check
        if section:
            ht_qs = AcademicLeadershipAssignment.objects.filter(
                teacher=teacher,
                role=AcademicLeadershipRole.HEAD_TEACHER,
                section=section,
                is_active=True,
            )
            if academic_year:
                ht_qs = ht_qs.filter(academic_year=academic_year)
            if ht_qs.exists():
                return True

        return False

    @classmethod
    def require_approval_authority(
        cls,
        *,
        actor,
        workflow: str,
        subject: Subject = None,
        department: Department = None,
        section: str = None,
        academic_year: AcademicYear = None,
        creator=None,
    ):
        """
        Raises PermissionDenied if the actor lacks approval authority.
        """
        if not cls.can_approve(
            actor=actor,
            workflow=workflow,
            subject=subject,
            department=department,
            section=section,
            academic_year=academic_year,
            creator=creator,
        ):
            teacher = cls.get_teacher(actor)
            if creator is not None and teacher and cls.get_teacher(creator) == teacher:
                raise PermissionDenied("Self-approval is prohibited for academic reviews.")
            raise PermissionDenied(
                f"You do not have academic review authority for this {workflow}."
            )
