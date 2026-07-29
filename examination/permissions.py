from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    """Compute, approve, publish, lock/unlock, generate reports, manage grading schemes."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_admin)


class IsTeacher(BasePermission):
    """Base check — user has a linked Teacher profile."""
    def has_permission(self, request, view):
        return bool(request.user and hasattr(request.user, "teacher"))


class CanComputeResults(BasePermission):
    """Admin or Teacher computing results for a student or classroom."""
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_admin or hasattr(request.user, "teacher"))
        )


class CanEnterScores(BasePermission):
    """
    Teacher entering/editing scores for their own allocated subjects,
    or Admin entering on a teacher's behalf.
    Row-level allocation (teacher actually assigned to this subject/class)
    is still enforced by AssessmentEntry.clean() regardless of this passing.
    """
    def has_permission(self, request, view):
        return bool(
            request.user.is_authenticated
            and (hasattr(request.user, "teacher") or request.user.is_admin)
        )

    def has_object_permission(self, request, view, obj):
        if request.user.is_admin:
            return True
        return obj.entered_by_id == request.user.teacher.id


class IsHomeroomTeacherOfClass(BasePermission):
    """Homeroom teacher acting on their own class's TermResult only."""
    def has_object_permission(self, request, view, obj):
        teacher = getattr(request.user, "teacher", None)
        return bool(teacher) and obj.classroom.class_teacher_id == teacher.id


class CanAddHomeroomRemarks(BasePermission):
    def has_permission(self, request, view):
        return hasattr(request.user, "teacher")

    def has_object_permission(self, request, view, obj):
        return IsHomeroomTeacherOfClass().has_object_permission(request, view, obj)


class CanHomeroomApprove(BasePermission):
    """Only the homeroom teacher of that specific class — admin does not bypass this step."""
    def has_permission(self, request, view):
        return hasattr(request.user, "teacher")

    def has_object_permission(self, request, view, obj):
        return IsHomeroomTeacherOfClass().has_object_permission(request, view, obj)


class CanApproveResults(IsAdmin):
    """Admin final approval — TermResult.approve() itself still blocks if homeroom_approved is False."""
    pass


class CanPublishResults(IsAdmin):
    pass


class CanLockResults(IsAdmin):
    pass


class CanGenerateReports(IsAdmin):
    pass


from rest_framework.permissions import BasePermission, SAFE_METHODS

class CanManageGradingScheme(BasePermission):
    """GradingScheme, AssessmentComponent, GradeRule, PromotionRule — admin-only setup. Teachers can view them."""
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return bool(request.user and request.user.is_authenticated and request.user.is_admin)


class CanUploadMarkedScript(BasePermission):
    def has_permission(self, request, view):
        return hasattr(request.user, "teacher") or request.user.is_admin

    def has_object_permission(self, request, view, obj):
        if request.user.is_admin:
            return True
        return obj.uploaded_by_id == request.user.teacher.id
    
class CanViewOwnStudentResult(BasePermission):
    """
    Allow Admin, Teacher (Homeroom or Subject teacher), or Student/Parent to view a TermResult detail.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if user.is_admin:
            return True

        if hasattr(user, "teacher"):
            teacher = user.teacher
            if obj.classroom and obj.classroom.class_teacher_id == teacher.id:
                return True
            if obj.subject_results.filter(teacher=teacher).exists():
                return True
            return False

        if user.is_student and user.active_role == "student":
            profile = getattr(user, "student_profile", None)
            return bool(profile) and obj.student_id == profile.id and obj.can_view

        if user.is_parent and user.active_role == "parent":
            parent = getattr(user, "parent", None)
            return bool(parent) and obj.student.parent_guardian_id == parent.id and obj.can_view

        return False


class CanViewMarkedScript(BasePermission):
    def has_object_permission(self, request, view, obj):
        user = request.user

        if user.is_student and user.active_role == "student":
            profile = getattr(user, "student_profile", None)
            return bool(profile) and obj.student_id == profile.id and obj.visible_to_student

        if user.is_parent and user.active_role == "parent":
            parent = getattr(user, "parent", None)
            return bool(parent) and obj.student.parent_guardian_id == parent.id and obj.visible_to_parent

        return False