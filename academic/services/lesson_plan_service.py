from academic.models import LessonPlanStatus
from django.core.exceptions import ValidationError
from django.utils import timezone


class LessonPlanService:

    @staticmethod
    def validate_context(
        *,
        scheme_item,
        allocation,
    ):
        scheme = scheme_item.scheme
        curriculum_subject = scheme.curriculum_subject

        if (
            allocation.subject_id
            != curriculum_subject.subject_id
        ):
            raise ValidationError(
                "Teacher allocation subject does not "
                "match the scheme of work."
            )

        allocation_grade = (
            allocation.class_room.grade_level
        )

        if (
            allocation_grade.id
            != curriculum_subject.grade_level_id
        ):
            raise ValidationError(
                "Teacher allocation grade level does "
                "not match the scheme of work."
            )

        if (
            allocation.academic_year_id
            != scheme.academic_year_id
        ):
            raise ValidationError(
                "Teacher allocation academic year does "
                "not match the scheme of work."
            )

        if (
            allocation.term_id
            and allocation.term_id
            != scheme.term_id
        ):
            raise ValidationError(
                "Teacher allocation term does not "
                "match the scheme of work."
            )

    @staticmethod
    def validate_objectives(
        *,
        scheme_item,
        objectives,
    ):
        allowed_ids = set(
            scheme_item.learning_objectives.values_list(
                "id",
                flat=True,
            )
        )

        submitted_ids = {
            objective.id
            for objective in objectives
        }

        if not submitted_ids.issubset(allowed_ids):
            raise ValidationError(
                "Lesson-plan objectives must belong to "
                "the selected scheme-of-work item."
            )

    @staticmethod
    def validate_subtopics(
        *,
        scheme_item,
        subtopics,
    ):
        allowed_ids = set(
            scheme_item.subtopics.values_list(
                "id",
                flat=True,
            )
        )

        submitted_ids = {
            subtopic.id
            for subtopic in subtopics
        }

        if not submitted_ids.issubset(allowed_ids):
            raise ValidationError(
                "Lesson-plan subtopics must belong to "
                "the selected scheme-of-work item."
            )

    @staticmethod
    def submit(plan):
        if plan.status != LessonPlanStatus.DRAFT:
            raise ValidationError(
                "Only draft lesson plans can be submitted."
            )

        plan.status = LessonPlanStatus.SUBMITTED
        plan.submitted_at = timezone.now()
        plan.rejection_reason = ""


        plan.save(
            update_fields=[
                "status",
                "submitted_at",
                "updated_at",
                "rejection_reason",
            ]
        )

    @staticmethod
    def approve(plan, *, reviewed_by):
        if not reviewed_by:
            raise ValidationError("Actor is required to approve a lesson plan.")

        if plan.status != LessonPlanStatus.SUBMITTED:
            raise ValidationError(
                "Only submitted lesson plans can be approved."
            )

        from academic.models import AcademicWorkflow
        from .academic_authority_service import AcademicAuthorityService

        subject = plan.allocation.subject
        section = plan.allocation.class_room.grade_level.section
        academic_year = plan.allocation.academic_year
        creator = plan.allocation.teacher_name

        AcademicAuthorityService.require_approval_authority(
            actor=reviewed_by,
            workflow=AcademicWorkflow.LESSON_PLAN,
            subject=subject,
            section=section,
            academic_year=academic_year,
            creator=creator,
        )

        reviewer = AcademicAuthorityService.get_teacher(reviewed_by)

        plan.status = LessonPlanStatus.APPROVED
        plan.reviewed_by = reviewer
        plan.reviewed_at = timezone.now()
        plan.rejection_reason = ""

        plan.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "rejection_reason",
                "updated_at",
            ]
        )

    @staticmethod
    def reject(
        plan,
        *,
        reviewed_by,
        reason,
    ):
        if not reviewed_by:
            raise ValidationError("Actor is required to reject a lesson plan.")

        if plan.status != LessonPlanStatus.SUBMITTED:
            raise ValidationError(
                "Only submitted lesson plans can be rejected."
            )

        reason = (reason or "").strip()

        if not reason:
            raise ValidationError(
                "A rejection reason is required."
            )

        from academic.models import AcademicWorkflow
        from .academic_authority_service import AcademicAuthorityService

        subject = plan.allocation.subject
        section = plan.allocation.class_room.grade_level.section
        academic_year = plan.allocation.academic_year
        creator = plan.allocation.teacher_name

        AcademicAuthorityService.require_approval_authority(
            actor=reviewed_by,
            workflow=AcademicWorkflow.LESSON_PLAN,
            subject=subject,
            section=section,
            academic_year=academic_year,
            creator=creator,
        )

        reviewer = AcademicAuthorityService.get_teacher(reviewed_by)

        plan.status = LessonPlanStatus.REJECTED
        plan.reviewed_by = reviewer
        plan.reviewed_at = timezone.now()
        plan.rejection_reason = reason

        plan.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "rejection_reason",
                "updated_at",
            ]
        )

    @staticmethod
    def reopen_for_revision(plan):
        if plan.status != LessonPlanStatus.REJECTED:
            raise ValidationError(
                "Only rejected lesson plans can be "
                "reopened for revision."
            )

        plan.status = LessonPlanStatus.DRAFT
        plan.submitted_at = None
        plan.reviewed_by = None
        plan.reviewed_at = None

        # Keep rejection_reason so the teacher can see
        # what needs to be corrected.

        plan.save(
            update_fields=[
                "status",
                "submitted_at",
                "reviewed_by",
                "reviewed_at",
                "updated_at",
            ]
        )
    