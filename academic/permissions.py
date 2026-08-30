"""
Custom Permissions - Phase 1.6: Student Portal

Permissions for:
- Student access control (students can only view their own data)
- Parent access control (parents can view their children's data)
- Combined student/parent access
"""
from rest_framework import permissions
from rest_framework.permissions import SAFE_METHODS


class IsStudentOwner(permissions.BasePermission):
    """
    Permission to allow students to only access their own data and classroom assignments.

    Usage:
    - Student can view/edit their own profile
    - Student can view their own results, attendance, assignments
    """

    def has_permission(self, request, view):
        """Check if user is authenticated and is a student"""
        return request.user and request.user.is_authenticated and (
            request.user.is_student or getattr(request.user, 'active_role', '') == 'student'
        )

    def has_object_permission(self, request, view, obj):
        """Check if student owns the object or object is for their classroom"""
        # If object is the student themselves
        if hasattr(obj, 'user') and obj.user:
            return obj.user == request.user

        # Get student profile for user
        student = getattr(request.user, 'student_profile', None) or getattr(request.user, 'student', None)
        if not student:
            from academic.models import Student
            student = Student.objects.filter(user=request.user).first()

        if not student:
            return False

        # If object is an Assignment for the student's classroom
        if hasattr(obj, 'classroom') and obj.classroom_id:
            return obj.classroom_id == student.classroom_id

        # If object belongs to the student (e.g., AttendanceRecord, Submission)
        if hasattr(obj, 'student') and obj.student_id:
            return obj.student_id == student.id

        return False



class IsParentOfStudent(permissions.BasePermission):
    """
    Permission to allow parents to view their children's data.

    Usage:
    - Parent can view their child's profile, results, attendance
    - Parent cannot view other children's data
    """

    def has_permission(self, request, view):
        """Check if user is authenticated and is a parent"""
        return request.user and request.user.is_authenticated and request.user.is_parent

    def has_object_permission(self, request, view, obj):
        """Check if parent is guardian of the student"""
        # Get student from object
        student = None

        if hasattr(obj, 'student'):
            # Object has direct student field (AttendanceRecord, Assignment, etc.)
            student = obj.student
        elif obj.__class__.__name__ == 'Student':
            # Object is the student themselves
            student = obj
        else:
            return False

        # Check if user is parent of this student
        if hasattr(request.user, 'parent'):
            parent = request.user.parent
            return student.parent_guardian == parent

        return False


class IsStudentOrParent(permissions.BasePermission):
    """
    Permission to allow either the student themselves OR their parent to access data.

    Usage:
    - Assignments: Student can view/submit, parent can view
    - Results: Student can view, parent can view
    - Attendance: Student can view, parent can view
    """

    def has_permission(self, request, view):
        """Check if user is authenticated and is either student or parent"""
        return (
            request.user and
            request.user.is_authenticated and
            (request.user.is_student or request.user.is_parent)
        )

    def has_object_permission(self, request, view, obj):
        """Check if user is the student OR parent of the student"""
        # Get student from object
        student = None

        if hasattr(obj, 'student'):
            student = obj.student
        elif obj.__class__.__name__ == 'Student':
            student = obj
        else:
            return False

        # Check if user is the student
        if request.user.is_student and hasattr(request.user, 'student_profile'):
            if request.user.student_profile == student:
                return True

        # Check if user is parent of the student
        if request.user.is_parent and hasattr(request.user, 'parent'):
            parent = request.user.parent
            if student.parent_guardian == parent:
                return True

        return False


class IsAdminOrStudentOwner(permissions.BasePermission):
    """
    Permission to allow admins OR the student themselves to access data.

    Usage:
    - Admin can manage all students
    - Student can view/edit their own data
    """

    def has_permission(self, request, view):
        """Check if user is authenticated"""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        """Check if user is admin OR student owner"""
        # Admin can access everything
        from academic.services.academic_authority_service import AcademicAuthorityService
        if AcademicAuthorityService.is_school_admin(request.user):
            return True

        # Student can access their own data
        if request.user.is_student:
            is_student_owner = IsStudentOwner()
            return is_student_owner.has_object_permission(request, view, obj)

        return False


class IsAdminOrParent(permissions.BasePermission):
    """
    Permission to allow admins OR parents to access data.

    Usage:
    - Admin can manage all students
    - Parent can view their children's data
    """

    def has_permission(self, request, view):
        """Check if user is authenticated"""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        """Check if user is admin OR parent of student"""
        # Admin can access everything
        from academic.services.academic_authority_service import AcademicAuthorityService
        if AcademicAuthorityService.is_school_admin(request.user):
            return True

        # Parent can access their children's data
        if request.user.is_parent:
            is_parent = IsParentOfStudent()
            return is_parent.has_object_permission(request, view, obj)

        return False


class IsAdminOrStudentOrParent(permissions.BasePermission):
    """
    Permission to allow admins, students, OR parents to access data.

    Usage:
    - Admin can manage everything
    - Student can view their own data
    - Parent can view their children's data
    """

    def has_permission(self, request, view):
        """Check if user is authenticated"""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        """Check if user is admin, student owner, OR parent"""
        # Admin can access everything
        from academic.services.academic_authority_service import AcademicAuthorityService
        if AcademicAuthorityService.is_school_admin(request.user):
            return True

        # Student or parent can access
        is_student_or_parent = IsStudentOrParent()
        return is_student_or_parent.has_object_permission(request, view, obj)


class CanAccessStudentPortal(permissions.BasePermission):
    """
    Permission to check if student is allowed to access portal.

    Usage:
    - Check if student has can_login=True
    - Check if student account is active
    """

    def has_permission(self, request, view):
        """Check if user is authenticated and is a student"""
        if not (request.user and request.user.is_authenticated and request.user.is_student):
            return False

        # Check if student profile exists
        if not hasattr(request.user, 'student_profile'):
            return False

        student = request.user.student_profile

        # Check if student is allowed to login
        if not student.can_login:
            return False

        # Check if student is active
        if not student.is_active:
            return False

        return True


def can_view_staff_salary(request_user, target_user=None) -> bool:
    """
    Evaluates whether the requesting user is authorized to view staff salary information.
    - Superusers and School Administrators (is_admin=True) can view.
    - Other roles (including the employee viewing their own record) cannot view.
    """
    if not request_user or not request_user.is_authenticated:
        return False
    from academic.services.academic_authority_service import AcademicAuthorityService
    return AcademicAuthorityService.is_school_admin(request_user)


class IsSchoolAdmin(permissions.BasePermission):
    """Allows access only to authenticated school administrators."""
    def has_permission(self, request, view):
        from academic.services.academic_authority_service import AcademicAuthorityService
        return bool(request.user and request.user.is_authenticated and AcademicAuthorityService.is_school_admin(request.user))


class IsAcademicAdminOrReadOnly(permissions.BasePermission):
    """Authenticated users may read academic structure; only school admins may mutate it."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        from academic.services.academic_authority_service import AcademicAuthorityService
        return AcademicAuthorityService.is_school_admin(request.user)


class IsAcademicPlanningUser(permissions.BasePermission):
    """Authenticated school admins and teachers may enter planning endpoints."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        from academic.services.academic_authority_service import AcademicAuthorityService
        return bool(
            AcademicAuthorityService.is_school_admin(request.user)
            or AcademicAuthorityService.get_teacher(request.user)
        )


class CanReviewLessonPlan(permissions.BasePermission):
    """Checks whether the requesting user has authority to approve/reject a lesson plan."""
    def has_object_permission(self, request, view, obj):
        from academic.models import AcademicWorkflow
        from academic.services.academic_authority_service import AcademicAuthorityService

        subject = obj.allocation.subject
        section = obj.allocation.class_room.grade_level.section
        academic_year = obj.allocation.academic_year
        creator = obj.allocation.teacher_name

        return AcademicAuthorityService.can_approve(
            actor=request.user,
            workflow=AcademicWorkflow.LESSON_PLAN,
            subject=subject,
            section=section,
            academic_year=academic_year,
            creator=creator,
        )


class CanReviewSchemeOfWork(permissions.BasePermission):
    """Checks whether the requesting user has authority to approve/reject a scheme of work."""
    def has_object_permission(self, request, view, obj):
        from academic.models import AcademicWorkflow
        from academic.services.academic_authority_service import AcademicAuthorityService

        subject = obj.curriculum_subject.subject
        section = obj.curriculum_subject.grade_level.section
        academic_year = obj.academic_year
        creator = obj.responsible_teacher

        return AcademicAuthorityService.can_approve(
            actor=request.user,
            workflow=AcademicWorkflow.SCHEME_OF_WORK,
            subject=subject,
            section=section,
            academic_year=academic_year,
            creator=creator,
        )
