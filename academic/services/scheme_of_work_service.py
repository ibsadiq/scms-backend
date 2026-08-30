from django.core.exceptions import ValidationError
from django.utils import timezone
from academic.models import SchemeOfWorkStatus, AcademicWorkflow
from .academic_authority_service import AcademicAuthorityService


class SchemeOfWorkService:

    @staticmethod
    def validate_item(
        *,
        scheme,
        curriculum_topic,
        subtopics,
        learning_objectives,
    ):
        subtopics = list(subtopics or [])
        learning_objectives = list(learning_objectives or [])
        if curriculum_topic is None:
            if subtopics or learning_objectives:
                raise ValidationError(
                    "A curriculum topic is required when subtopics or objectives are selected."
                )
            return

        if (
            curriculum_topic.curriculum_subject_id
            != scheme.curriculum_subject_id
        ):
            raise ValidationError(
                "Curriculum topic must belong to the "
                "scheme's curriculum subject."
            )

        allowed_subtopic_ids = set(
            curriculum_topic.topic.subtopics
            .filter(is_active=True)
            .values_list("id", flat=True)
        )

        submitted_subtopic_ids = {
            item.id for item in subtopics
        }

        if not submitted_subtopic_ids.issubset(
            allowed_subtopic_ids
        ):
            raise ValidationError(
                "One or more subtopics do not belong "
                "to the selected topic."
            )

        allowed_objective_ids = set(
            curriculum_topic.learning_objectives
            .filter(is_active=True)
            .values_list("id", flat=True)
        )

        submitted_objective_ids = {
            objective.id
            for objective in learning_objectives
        }

        if not submitted_objective_ids.issubset(
            allowed_objective_ids
        ):
            raise ValidationError(
                "One or more learning objectives do "
                "not belong to the selected curriculum topic."
            )

    @staticmethod
    def submit(scheme, actor=None):
        if scheme.status != SchemeOfWorkStatus.DRAFT:
            raise ValidationError("Only draft schemes of work can be submitted.")

        scheme.status = SchemeOfWorkStatus.SUBMITTED
        scheme.submitted_at = timezone.now()
        scheme.rejection_reason = ""
        scheme.save(
            update_fields=[
                "status",
                "submitted_at",
                "rejection_reason",
                "updated_at",
            ]
        )
        return scheme

    @staticmethod
    def approve(scheme, *, actor):
        if not actor:
            raise ValidationError("Actor is required to approve a scheme of work.")

        if scheme.status != SchemeOfWorkStatus.SUBMITTED:
            raise ValidationError("Only submitted schemes of work can be approved.")

        # Authority & Self-approval verification
        subject = scheme.curriculum_subject.subject
        section = scheme.curriculum_subject.grade_level.section
        AcademicAuthorityService.require_approval_authority(
            actor=actor,
            workflow=AcademicWorkflow.SCHEME_OF_WORK,
            subject=subject,
            section=section,
            academic_year=scheme.academic_year,
            creator=scheme.responsible_teacher,
        )

        reviewer = AcademicAuthorityService.get_teacher(actor)
        scheme.status = SchemeOfWorkStatus.APPROVED
        scheme.reviewed_by = reviewer
        scheme.reviewed_at = timezone.now()
        scheme.rejection_reason = ""
        scheme.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "rejection_reason",
                "updated_at",
            ]
        )
        return scheme

    @staticmethod
    def reject(scheme, *, actor, reason: str):
        if not actor:
            raise ValidationError("Actor is required to reject a scheme of work.")

        if scheme.status != SchemeOfWorkStatus.SUBMITTED:
            raise ValidationError("Only submitted schemes of work can be rejected.")

        reason = (reason or "").strip()
        if not reason:
            raise ValidationError("A rejection reason is required.")

        subject = scheme.curriculum_subject.subject
        section = scheme.curriculum_subject.grade_level.section
        AcademicAuthorityService.require_approval_authority(
            actor=actor,
            workflow=AcademicWorkflow.SCHEME_OF_WORK,
            subject=subject,
            section=section,
            academic_year=scheme.academic_year,
            creator=scheme.responsible_teacher,
        )

        reviewer = AcademicAuthorityService.get_teacher(actor)
        scheme.status = SchemeOfWorkStatus.REJECTED
        scheme.reviewed_by = reviewer
        scheme.reviewed_at = timezone.now()
        scheme.rejection_reason = reason
        scheme.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "rejection_reason",
                "updated_at",
            ]
        )
        return scheme

    @staticmethod
    def reopen_for_revision(scheme):
        if scheme.status != SchemeOfWorkStatus.REJECTED:
            raise ValidationError("Only rejected schemes of work can be reopened for revision.")

        scheme.status = SchemeOfWorkStatus.DRAFT
        scheme.submitted_at = None
        scheme.reviewed_by = None
        scheme.reviewed_at = None
        scheme.save(
            update_fields=[
                "status",
                "submitted_at",
                "reviewed_by",
                "reviewed_at",
                "updated_at",
            ]
        )
        return scheme
