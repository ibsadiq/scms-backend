from rest_framework.permissions import BasePermission
from django.core.exceptions import ValidationError, ObjectDoesNotExist

from academic.models import AllocatedSubject, AcademicWorkflow
from academic.services.academic_authority_service import AcademicAuthorityService
from cbt.services.cbt_actor_service import CBTActorService


class CanGradeCBTExam(BasePermission):
    """
    Permission for grading essays and viewing manual grading queue.
    Allows Admins, HODs, Head Teachers, or Teachers allocated to the subject/classroom.
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

        # Resolve subject, classroom, academic_year from AttemptQuestion or ExamAttempt or AttemptGrade
        attempt = getattr(obj, "attempt", None)
        if attempt is None and hasattr(obj, "exam"):
            attempt = obj

        if not attempt:
            return False

        exam = attempt.cbt_exam if hasattr(attempt, "cbt_exam") else getattr(attempt, "exam", None)
        if not exam:
            return False

        subject = exam.subject
        classroom = exam.classroom

        # Check teacher allocation
        if subject and classroom:
            if AllocatedSubject.objects.filter(
                teacher_name=teacher,
                subject=subject,
                class_room=classroom,
            ).exists():
                return True

        # Check leadership authority
        section = None
        if classroom and hasattr(classroom.name, "grade_level"):
            section = classroom.name.grade_level.section

        academic_year = None
        if exam.session and hasattr(exam.session, "academic_year"):
            academic_year = exam.session.academic_year

        return AcademicAuthorityService.can_approve(
            actor=request.user,
            workflow=AcademicWorkflow.CBT_PUBLISH,
            subject=subject,
            section=section,
            academic_year=academic_year,
            creator=exam.created_by,
        )


class CanPostCBTResult(BasePermission):
    """
    Permission for posting CBT results to assessment entries.
    Allows Admins or authorized teachers.
    Students and parents are strictly forbidden.
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

        attempt = getattr(obj, "attempt", None)
        if not attempt:
            return False

        exam = attempt.cbt_exam if hasattr(attempt, "cbt_exam") else getattr(attempt, "exam", None)
        if not exam:
            return False

        subject = exam.subject
        classroom = exam.classroom

        if subject and classroom:
            if AllocatedSubject.objects.filter(
                teacher_name=teacher,
                subject=subject,
                class_room=classroom,
            ).exists():
                return True

        section = None
        if classroom and hasattr(classroom.name, "grade_level"):
            section = classroom.name.grade_level.section

        academic_year = None
        if exam.session and hasattr(exam.session, "academic_year"):
            academic_year = exam.session.academic_year

        return AcademicAuthorityService.can_approve(
            actor=request.user,
            workflow=AcademicWorkflow.CBT_PUBLISH,
            subject=subject,
            section=section,
            academic_year=academic_year,
            creator=exam.created_by,
        )
