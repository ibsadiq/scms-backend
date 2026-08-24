from rest_framework.permissions import BasePermission, SAFE_METHODS
from django.core.exceptions import ValidationError, ObjectDoesNotExist

from academic.models import AllocatedSubject, AcademicWorkflow
from academic.services.academic_authority_service import AcademicAuthorityService
from cbt.services.cbt_actor_service import CBTActorService


class CanManageCBTExam(BasePermission):
    """
    Permission for managing CBT exams and blueprints.
    Allows Admins, HODs, Head Teachers, or Teachers allocated to the subject/class.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if AcademicAuthorityService.is_school_admin(request.user):
            return True

        try:
            teacher = CBTActorService.resolve_teacher(request.user)
            return teacher is not None
        except (ValidationError, ObjectDoesNotExist):
            return False

    def has_object_permission(self, request, view, obj):
        if AcademicAuthorityService.is_school_admin(request.user):
            return True

        try:
            teacher = CBTActorService.resolve_teacher(request.user)
        except (ValidationError, ObjectDoesNotExist):
            return False

        # Read permissions allowed to staff/teachers
        if request.method in SAFE_METHODS:
            return True

        # Check if creator
        creator = getattr(obj, "created_by", None)
        if creator and creator == teacher:
            return True

        # Check if teacher is allocated to the subject and classroom
        subject = getattr(obj, "subject", None)
        classroom = getattr(obj, "classroom", None)

        if subject and classroom:
            is_allocated = AllocatedSubject.objects.filter(
                teacher_name=teacher,
                subject=subject,
                class_room=classroom,
            ).exists()
            if is_allocated:
                return True

        # Check leadership authority
        section = None
        if classroom and hasattr(classroom.name, "grade_level"):
            section = classroom.name.grade_level.section

        academic_year = None
        session = getattr(obj, "session", None)
        if session and hasattr(session, "academic_year"):
            academic_year = session.academic_year

        return AcademicAuthorityService.can_approve(
            actor=request.user,
            workflow=AcademicWorkflow.CBT_PUBLISH,
            subject=subject,
            section=section,
            academic_year=academic_year,
            creator=creator,
        )


class CanPublishCBTExam(BasePermission):
    """
    Permission for publishing CBT exams.
    Strictly delegates to AcademicAuthorityService under CBT_PUBLISH workflow.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return True

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        subject = getattr(obj, "subject", None)
        classroom = getattr(obj, "classroom", None)
        creator = getattr(obj, "created_by", None)

        section = None
        if classroom and hasattr(classroom.name, "grade_level"):
            section = classroom.name.grade_level.section

        academic_year = None
        session = getattr(obj, "session", None)
        if session and hasattr(session, "academic_year"):
            academic_year = session.academic_year

        return AcademicAuthorityService.can_approve(
            actor=request.user,
            workflow=AcademicWorkflow.CBT_PUBLISH,
            subject=subject,
            section=section,
            academic_year=academic_year,
            creator=creator,
        )
