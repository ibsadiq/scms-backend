from django.core.exceptions import ValidationError
from django.db import transaction

from cbt.models import (
    CBTExam,
    CBTExamStatus,
)
from academic.models import AcademicWorkflow
from academic.services.academic_authority_service import AcademicAuthorityService


class CBTExamService:

    @staticmethod
    @transaction.atomic
    def publish(*, exam, actor):
        if not actor:
            raise ValidationError("Actor is required to publish a CBT exam.")

        exam = (
            CBTExam.objects
            .select_for_update()
            .get(pk=exam.pk)
        )

        CBTExamService.validate_for_publish(exam)

        section = None
        if exam.classroom and hasattr(exam.classroom, 'grade_level') and exam.classroom.grade_level:
            section = exam.classroom.grade_level.section

        academic_year = None
        if exam.session and hasattr(exam.session, 'academic_year'):
            academic_year = exam.session.academic_year

        AcademicAuthorityService.require_approval_authority(
            actor=actor,
            workflow=AcademicWorkflow.CBT_PUBLISH,
            subject=exam.subject,
            section=section,
            academic_year=academic_year,
            creator=exam.created_by,
        )

        exam.status = CBTExamStatus.PUBLISHED

        exam.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        return exam

    @staticmethod
    @transaction.atomic
    def close(*, exam):
        exam = (
            CBTExam.objects
            .select_for_update()
            .get(pk=exam.pk)
        )

        if exam.status != CBTExamStatus.PUBLISHED:
            raise ValidationError(
                "Only a published CBT exam can be closed."
            )

        exam.status = CBTExamStatus.CLOSED

        exam.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        return exam

    @staticmethod
    @transaction.atomic
    def reset_to_draft(*, exam):
        exam = (
            CBTExam.objects
            .select_for_update()
            .get(pk=exam.pk)
        )

        if exam.status != CBTExamStatus.READY:
            raise ValidationError(
                "Only a ready CBT exam can be reset to draft."
            )

        if exam.attempts.exists():
            raise ValidationError(
                "Cannot reset CBT exam to draft because exam attempts already exist."
            )

        blueprint = (
            exam.blueprint.__class__.objects
            .select_for_update()
            .get(pk=exam.blueprint.pk)
        )

        exam.exam_questions.all().delete()

        blueprint.is_locked = False
        blueprint.save(
            update_fields=[
                "is_locked",
                "updated_at",
            ]
        )

        exam.status = CBTExamStatus.DRAFT
        exam.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        return exam

    @staticmethod
    def ensure_draft(exam):
        if exam.status != CBTExamStatus.DRAFT:
            raise ValidationError(
                "This action is only allowed while "
                "the CBT exam is in draft status."
            )

    @staticmethod
    def ensure_not_published(exam):
        if exam.status in {
            CBTExamStatus.PUBLISHED,
            CBTExamStatus.CLOSED,
        }:
            raise ValidationError(
                "Published or closed CBT exams "
                "cannot be modified."
            )

    @staticmethod
    def validate_for_publish(exam):
        if exam.status != CBTExamStatus.READY:
            raise ValidationError(
                "Only a ready CBT exam can be published."
            )

        exam_questions = exam.exam_questions.all()

        if not exam_questions.exists():
            raise ValidationError(
                "A CBT exam cannot be published without questions."
            )

        if exam_questions.filter(marks__lte=0).exists():
            raise ValidationError(
                "Every exam question must have marks "
                "greater than zero."
            )

        return True