from rest_framework.permissions import BasePermission, SAFE_METHODS
from django.core.exceptions import ValidationError, ObjectDoesNotExist

from academic.models import AcademicWorkflow
from academic.services.academic_authority_service import AcademicAuthorityService
from cbt.services.cbt_actor_service import CBTActorService


class CanManageQuestionBank(BasePermission):
    """
    Permission for managing Question Bank items.
    Allows Teachers and Admins to manage question banks, create questions, and versions.
    Blocks Students and Parents.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if AcademicAuthorityService.is_school_admin(request.user):
            return True

        try:
            teacher = CBTActorService.resolve_teacher(request.user)
            return teacher is not None
        except Exception:
            return False

    def has_object_permission(self, request, view, obj):
        if AcademicAuthorityService.is_school_admin(request.user):
            return True

        try:
            teacher = CBTActorService.resolve_teacher(request.user)
        except (ValidationError, ObjectDoesNotExist):
            return False

        # Read permissions are allowed to any authenticated teacher
        if request.method in SAFE_METHODS:
            return True

        # Mutation permissions on questions
        creator = getattr(obj, "created_by", None)
        if creator and creator == teacher:
            return True

        # Or if the teacher has leadership authority for this question's subject
        subject = getattr(obj, "subject", None)
        if subject and AcademicAuthorityService.can_approve(
            actor=request.user,
            workflow=AcademicWorkflow.QUESTION_BANK,
            subject=subject,
            creator=creator,
        ):
            return True

        return False


class CanReviewQuestion(BasePermission):
    """
    Permission for reviewing/approving/rejecting questions.
    Delegates strictly to AcademicAuthorityService under QUESTION_BANK workflow.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return True

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        subject = getattr(obj, "subject", None)
        creator = getattr(obj, "created_by", None)

        return AcademicAuthorityService.can_approve(
            actor=request.user,
            workflow=AcademicWorkflow.QUESTION_BANK,
            subject=subject,
            creator=creator,
        )
