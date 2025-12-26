"""
Custom Permissions for Examination Module (Phase 1.3)
Handles authorization for marks entry, result viewing, and publishing.
"""
from rest_framework import permissions
from academic.models import AllocatedSubject


class CanEnterMarks(permissions.BasePermission):
    """
    Permission to check if a teacher can enter marks for a specific subject and classroom.

    Rules:
    - Admins can enter marks for any subject/classroom
    - Teachers can only enter marks for subjects they are allocated to
    - Must have AllocatedSubject record linking teacher → subject → classroom
    """

    message = "You are not authorized to enter marks for this subject/classroom combination."

    def has_permission(self, request, view):
        """Check if user is authenticated and is staff"""
        if not request.user.is_authenticated:
            return False

        # Admins have full access
        if request.user.is_staff and request.user.is_superuser:
            return True

        # Teachers need to be staff
        return request.user.is_staff

    def has_object_permission(self, request, view, obj):
        """
        Check if teacher is allocated to the subject and classroom for this mark.

        Args:
            obj: MarksManagement instance
        """
        # Admins have full access
        if request.user.is_superuser:
            return True

        # Check if user has a teacher profile
        try:
            teacher = request.user.teacher
        except AttributeError:
            return False

        # Check if teacher is allocated to this subject and classroom
        # Get student's classroom
        student_classroom = obj.student.class_room if hasattr(obj.student, 'class_room') else None

        if not student_classroom:
            return False

        # Check allocation
        is_allocated = AllocatedSubject.objects.filter(
            teacher_name=teacher,
            subject=obj.subject,
            class_room=student_classroom
        ).exists()

        return is_allocated


class CanViewResults(permissions.BasePermission):
    """
    Permission to check if a user can view specific results.

    Rules:
    - Admins can view all results
    - Teachers can view results for their allocated subjects/classrooms
    - Parents can view only their children's published results
    - Students can view only their own published results
    """

    message = "You are not authorized to view these results."

    def has_permission(self, request, view):
        """Check if user is authenticated"""
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        """
        Check viewing permission based on user role.

        Args:
            obj: TermResult or SubjectResult instance
        """
        user = request.user

        # Admins have full access
        if user.is_superuser:
            return True

        # For TermResult or SubjectResult
        if hasattr(obj, 'student'):
            result_student = obj.student
        elif hasattr(obj, 'term_result'):
            result_student = obj.term_result.student
        else:
            return False

        # Teachers can view results for their allocated students
        if user.is_staff:
            try:
                teacher = user.teacher
                # Check if teacher is allocated to any subject in student's classroom
                student_classroom = result_student.classroom
                is_allocated = AllocatedSubject.objects.filter(
                    teacher_name=teacher,
                    class_room=student_classroom
                ).exists()

                if is_allocated:
                    return True
            except AttributeError:
                pass

        # Parents can view their children's published results
        try:
            parent = user.parent
            is_parent_of_student = result_student.parent_guardian == parent

            # Check if result is published
            is_published = obj.is_published if hasattr(obj, 'is_published') else obj.term_result.is_published

            return is_parent_of_student and is_published
        except AttributeError:
            pass

        # Students can view their own published results
        try:
            if hasattr(user, 'student') and user.student == result_student:
                is_published = obj.is_published if hasattr(obj, 'is_published') else obj.term_result.is_published
                return is_published
        except AttributeError:
            pass

        return False


class CanPublishResults(permissions.BasePermission):
    """
    Permission to publish or unpublish results.

    Rules:
    - Only admins and head teachers can publish/unpublish results
    - Regular teachers cannot publish results
    """

    message = "Only administrators and head teachers can publish results."

    def has_permission(self, request, view):
        """Check if user has admin privileges"""
        if not request.user.is_authenticated:
            return False

        # Superusers can always publish
        if request.user.is_superuser:
            return True

        # Check if user is head teacher (you can customize this logic)
        # For now, require superuser status
        return False


class CanManageExaminations(permissions.BasePermission):
    """
    Permission to create, update, or delete examinations/assessments.

    Rules:
    - Admins can manage all examinations
    - Teachers can only manage examinations for their allocated classrooms
    """

    message = "You are not authorized to manage this examination."

    def has_permission(self, request, view):
        """Check if user is authenticated and is staff"""
        if not request.user.is_authenticated:
            return False

        return request.user.is_staff

    def has_object_permission(self, request, view, obj):
        """
        Check if user can manage this specific examination.

        Args:
            obj: ExaminationListHandler instance
        """
        user = request.user

        # Admins have full access
        if user.is_superuser:
            return True

        # Check if user created this examination
        if obj.created_by == user:
            return True

        # Check if user is a teacher allocated to any of the examination's classrooms
        try:
            teacher = user.teacher
            exam_classrooms = obj.classrooms.all()

            for classroom in exam_classrooms:
                is_allocated = AllocatedSubject.objects.filter(
                    teacher_name=teacher,
                    class_room=classroom
                ).exists()

                if is_allocated:
                    return True
        except AttributeError:
            pass

        return False


class CanGenerateReportCards(permissions.BasePermission):
    """
    Permission to generate report cards.

    Rules:
    - Only admins can generate report cards
    - Teachers cannot generate report cards (prevents premature distribution)
    """

    message = "Only administrators can generate report cards."

    def has_permission(self, request, view):
        """Check if user is admin"""
        if not request.user.is_authenticated:
            return False

        return request.user.is_superuser


class IsTeacherOrAdmin(permissions.BasePermission):
    """
    Simple permission to check if user is a teacher or admin.
    Used for general teacher-specific endpoints.
    """

    message = "You must be a teacher or administrator."

    def has_permission(self, request, view):
        """Check if user is staff (teacher or admin)"""
        if not request.user.is_authenticated:
            return False

        return request.user.is_staff


class IsTeacherOfClass(permissions.BasePermission):
    """
    Permission to check if teacher is allocated to a specific classroom.
    """

    message = "You are not allocated to this classroom."

    def has_permission(self, request, view):
        """Check if user is authenticated and is staff"""
        if not request.user.is_authenticated:
            return False

        return request.user.is_staff

    def check_allocation(self, user, classroom):
        """
        Check if user is allocated to the given classroom.

        Args:
            user: CustomUser instance
            classroom: ClassRoom instance

        Returns:
            bool: True if allocated, False otherwise
        """
        # Admins are always "allocated"
        if user.is_superuser:
            return True

        try:
            teacher = user.teacher
            return AllocatedSubject.objects.filter(
                teacher_name=teacher,
                class_room=classroom
            ).exists()
        except AttributeError:
            return False


class IsParentOfStudent(permissions.BasePermission):
    """
    Permission to check if user is a parent and can access their child's data.

    Rules:
    - Only parents can access their children's information
    - Admins can access all data
    - Parents cannot access other children's data
    """

    message = "You can only access your own children's data."

    def has_permission(self, request, view):
        """Check if user is authenticated"""
        if not request.user.is_authenticated:
            return False

        # Admins have full access
        if request.user.is_superuser:
            return True

        # Check if user has a parent profile
        return hasattr(request.user, 'parent')

    def has_object_permission(self, request, view, obj):
        """
        Check if parent is viewing their own child's data.

        Args:
            obj: Student, TermResult, or other student-related instance
        """
        user = request.user

        # Admins have full access
        if user.is_superuser:
            return True

        try:
            parent = user.parent
        except AttributeError:
            return False

        # Determine the student from various object types
        student = None

        if hasattr(obj, 'student'):
            # For results, marks, attendance, etc.
            student = obj.student
        elif obj.__class__.__name__ == 'Student':
            # Direct student object
            student = obj
        elif hasattr(obj, 'term_result'):
            # For subject results
            student = obj.term_result.student

        if not student:
            return False

        # Check if this student is a child of this parent
        return student.parent_guardian == parent


class CanViewChildData(permissions.BasePermission):
    """
    Permission for parents to view their children's non-sensitive data.

    Rules:
    - Parents can view their children's information
    - Results must be published for parents to view
    - Attendance is always viewable by parents
    - Fee information is always viewable by parents
    """

    message = "You can only view your own children's data."

    def has_permission(self, request, view):
        """Check if user is authenticated and has parent profile"""
        if not request.user.is_authenticated:
            return False

        # Admins have full access
        if request.user.is_superuser:
            return True

        return hasattr(request.user, 'parent')

    def has_object_permission(self, request, view, obj):
        """
        Check if parent can view this specific data.
        Only published results are viewable by parents.
        """
        user = request.user

        # Admins have full access
        if user.is_superuser:
            return True

        try:
            parent = user.parent
        except AttributeError:
            return False

        # Determine student and check relationship
        student = None

        if hasattr(obj, 'student'):
            student = obj.student
        elif obj.__class__.__name__ == 'Student':
            student = obj
        elif hasattr(obj, 'term_result'):
            student = obj.term_result.student

        if not student or student.parent_guardian != parent:
            return False

        # For results, check if published
        if hasattr(obj, 'is_published'):
            return obj.is_published
        elif hasattr(obj, 'term_result') and hasattr(obj.term_result, 'is_published'):
            return obj.term_result.is_published

        # For other data (attendance, fees, etc.), allow access
        return True
