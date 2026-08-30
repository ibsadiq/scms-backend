from django.db.models import Q

from academic.models import AcademicLeadershipAssignment, AcademicLeadershipRole
from .academic_authority_service import AcademicAuthorityService


class AcademicPlanningAccessService:
    """Actor scoping and ownership rules for school-operational planning records."""

    @staticmethod
    def _teacher(actor):
        return AcademicAuthorityService.get_teacher(actor)

    @classmethod
    def scheme_scope(cls, actor):
        if AcademicAuthorityService.is_school_admin(actor):
            return Q()
        teacher = cls._teacher(actor)
        if not teacher:
            return Q(pk__in=[])

        scope = Q(responsible_teacher=teacher)
        assignments = AcademicLeadershipAssignment.objects.filter(
            teacher=teacher, is_active=True
        )
        for assignment in assignments:
            common = Q(academic_year=assignment.academic_year)
            if assignment.role == AcademicLeadershipRole.HOD:
                scope |= common & Q(
                    curriculum_subject__subject__department=assignment.department
                )
            elif assignment.role == AcademicLeadershipRole.HEAD_TEACHER:
                scope |= common & Q(
                    curriculum_subject__grade_level__section=assignment.section
                )
        return scope

    @classmethod
    def lesson_plan_scope(cls, actor):
        if AcademicAuthorityService.is_school_admin(actor):
            return Q()
        teacher = cls._teacher(actor)
        if not teacher:
            return Q(pk__in=[])

        scope = Q(allocation__teacher_name=teacher)
        assignments = AcademicLeadershipAssignment.objects.filter(
            teacher=teacher, is_active=True
        )
        for assignment in assignments:
            common = Q(allocation__academic_year=assignment.academic_year)
            if assignment.role == AcademicLeadershipRole.HOD:
                scope |= common & Q(allocation__subject__department=assignment.department)
            elif assignment.role == AcademicLeadershipRole.HEAD_TEACHER:
                scope |= common & Q(
                    allocation__class_room__grade_level__section=assignment.section
                )
        return scope

    @classmethod
    def can_manage_scheme(cls, actor, scheme):
        if AcademicAuthorityService.is_school_admin(actor):
            return True
        teacher = cls._teacher(actor)
        return bool(teacher and scheme.responsible_teacher_id == teacher.id)

    @classmethod
    def can_manage_plan(cls, actor, plan):
        if AcademicAuthorityService.is_school_admin(actor):
            return True
        teacher = cls._teacher(actor)
        return bool(teacher and plan.allocation.teacher_name_id == teacher.id)

    @classmethod
    def can_use_allocation(cls, actor, allocation):
        if AcademicAuthorityService.is_school_admin(actor):
            return True
        teacher = cls._teacher(actor)
        return bool(teacher and allocation.teacher_name_id == teacher.id)
