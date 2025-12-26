"""
Custom Permissions - Phase 1.6: Student Portal

Permissions for:
- Student access control (students can only view their own data)
- Parent access control (parents can view their children's data)
- Combined student/parent access
"""
from rest_framework import permissions


class IsStudentOwner(permissions.BasePermission):
    """
    Permission to allow students to only access their own data.

    Usage:
    - Student can view/edit their own profile
    - Student can view their own results, attendance, assignments
    """

    def has_permission(self, request, view):
        """Check if user is authenticated and is a student"""
        return request.user and request.user.is_authenticated and request.user.is_student

    def has_object_permission(self, request, view, obj):
        """Check if student owns the object"""
        # If object is the student themselves
        if hasattr(obj, 'user'):
            return obj.user == request.user

        # If object belongs to the student (e.g., AttendanceRecord, Assignment)
        if hasattr(obj, 'student'):
            return hasattr(request.user, 'student_profile') and obj.student == request.user.student_profile

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
        if request.user.is_staff:
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
        if request.user.is_staff:
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
        if request.user.is_staff:
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
