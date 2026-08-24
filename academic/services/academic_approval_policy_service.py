from django.core.exceptions import PermissionDenied, ValidationError
from academic.models import (
    AcademicWorkflow,
    ApprovalRoute,
    AcademicApprovalPolicy,
)


class AcademicApprovalPolicyService:
    """
    Manages tenant-level academic approval policy configurations per workflow.
    Defaults to ADMIN_ONLY if no policy record exists.
    """

    @classmethod
    def get_route(cls, workflow: str) -> str:
        """
        Returns the configured ApprovalRoute for a workflow, falling back to ADMIN_ONLY.
        """
        policy = AcademicApprovalPolicy.objects.filter(
            workflow=workflow,
            is_active=True,
        ).first()

        if policy:
            return policy.approval_route

        return ApprovalRoute.ADMIN_ONLY

    @classmethod
    def requires_academic_leader(cls, workflow: str) -> bool:
        """
        Returns True if the workflow permits/requires HOD / Head Teacher review.
        """
        route = cls.get_route(workflow)
        return route == ApprovalRoute.ACADEMIC_LEADER_OR_ADMIN

    @classmethod
    def set_route(
        cls,
        *,
        workflow: str,
        approval_route: str,
        actor=None,
    ) -> AcademicApprovalPolicy:
        """
        Configures the approval route for a specific academic workflow.
        Only school administrators can modify workflow policies.
        """
        if actor is not None:
            is_admin = getattr(actor, "is_admin", False) or getattr(actor, "is_staff", False) or getattr(actor, "is_superuser", False)
            if not is_admin:
                raise PermissionDenied("Only school administrators can change academic approval policies.")

        if workflow not in AcademicWorkflow.values:
            raise ValidationError(f"Invalid academic workflow: {workflow}")

        if approval_route not in ApprovalRoute.values:
            raise ValidationError(f"Invalid approval route: {approval_route}")

        policy, _ = AcademicApprovalPolicy.objects.update_or_create(
            workflow=workflow,
            defaults={
                "approval_route": approval_route,
                "is_active": True,
            },
        )
        return policy
