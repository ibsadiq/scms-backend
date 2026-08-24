from rest_framework.permissions import BasePermission
from django.core.exceptions import ValidationError, ObjectDoesNotExist

from academic.models import StudentClassEnrollment
from cbt.models import CBTExamStatus
from cbt.services.cbt_actor_service import CBTActorService


class CanTakeCBTExam(BasePermission):
    """
    Permission for taking a CBT exam.
    Validates that:
    - User is authenticated student
    - Exam is PUBLISHED
    - Student has active StudentClassEnrollment for the exam's classroom & academic year
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            student = CBTActorService.resolve_student(request.user)
            return student is not None
        except (ValidationError, ObjectDoesNotExist):
            return False

    def has_object_permission(self, request, view, obj):
        try:
            student = CBTActorService.resolve_student(request.user)
        except (ValidationError, ObjectDoesNotExist):
            return False

        exam = getattr(obj, "exam", obj)

        if exam.status != CBTExamStatus.PUBLISHED:
            return False

        academic_year = None
        if exam.session and hasattr(exam.session, "academic_year"):
            academic_year = exam.session.academic_year

        # Authoritative eligibility check via StudentClassEnrollment
        enrollment_qs = StudentClassEnrollment.objects.filter(
            student=student,
            classroom=exam.classroom,
            is_active=True,
        )
        if academic_year:
            enrollment_qs = enrollment_qs.filter(academic_year=academic_year)

        return enrollment_qs.exists()


class CanAccessOwnAttempt(BasePermission):
    """
    Permission for student accessing and interacting with their own CBT attempt.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            student = CBTActorService.resolve_student(request.user)
            return student is not None
        except (ValidationError, ObjectDoesNotExist):
            return False

    def has_object_permission(self, request, view, obj):
        try:
            student = CBTActorService.resolve_student(request.user)
        except (ValidationError, ObjectDoesNotExist):
            return False

        # If obj is ExamAttempt
        if hasattr(obj, "student"):
            return obj.student == student

        # If obj is AttemptQuestion
        if hasattr(obj, "attempt"):
            return obj.attempt.student == student

        return False
