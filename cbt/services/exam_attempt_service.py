import secrets
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from academic.models import StudentClassEnrollment

from ..models import (
    CBTExam,
    CBTExamStatus,
    ExamAttempt,
    ExamAttemptStatus,
    AttemptQuestion,
    AttemptQuestionOption,
    QuestionType,
)


_rng = secrets.SystemRandom()


class ExamAttemptService:

    # =========================================================
    # START ATTEMPT
    # =========================================================

    @staticmethod
    @transaction.atomic
    def start_attempt(
        *,
        exam,
        student,
    ):
        exam = (
            CBTExam.objects
            .select_for_update()
            .select_related(
                "session",
                "classroom",
            )
            .get(pk=exam.pk)
        )

        if exam.status != CBTExamStatus.PUBLISHED:
            raise ValidationError(
                "This CBT exam is not available."
            )

        existing_attempt = (
            ExamAttempt.objects
            .select_for_update()
            .filter(
                cbt_exam=exam,
                student=student,
            )
            .first()
        )

        if existing_attempt:
            if (
                existing_attempt.status
                == ExamAttemptStatus.IN_PROGRESS
            ):
                if ExamAttemptService.is_expired(
                    existing_attempt
                ):
                    return (
                        ExamAttemptService
                        ._handle_expiry(
                            attempt=existing_attempt
                        )
                    )

                raise ValidationError(
                    "You already have an active attempt "
                    "for this CBT exam."
                )

            if (
                existing_attempt.status
                == ExamAttemptStatus.SUBMITTED
            ):
                raise ValidationError(
                    "You have already submitted this CBT exam."
                )

            if (
                existing_attempt.status
                == ExamAttemptStatus.EXPIRED
            ):
                raise ValidationError(
                    "Your attempt for this CBT exam has expired."
                )

            raise ValidationError(
                "You already have an attempt for this CBT exam."
            )

        enrollment = (
            StudentClassEnrollment.objects
            .select_related(
                "student",
                "classroom",
                "academic_year",
            )
            .filter(
                student=student,
                academic_year=exam.session.academic_year,
                classroom=exam.classroom,
                is_active=True,
            )
            .first()
        )

        if enrollment is None:
            raise ValidationError(
                "Student is not eligible to take this CBT exam."
            )

        if not exam.exam_questions.exists():
            raise ValidationError(
                "This CBT exam does not contain any questions."
            )

        started_at = timezone.now()

        expires_at = (
            started_at
            + timedelta(
                minutes=exam.duration_minutes
            )
        )

        attempt = ExamAttempt.objects.create(
            cbt_exam=exam,
            student=student,
            enrollment=enrollment,
            status=ExamAttemptStatus.IN_PROGRESS,
            started_at=started_at,
            expires_at=expires_at,
            last_activity_at=started_at,
        )

        ExamAttemptService._create_attempt_questions(
            attempt=attempt,
        )

        return attempt

    # =========================================================
    # MATERIALIZE QUESTION ORDER
    # =========================================================

    @staticmethod
    def _create_attempt_questions(
        *,
        attempt,
    ):
        exam = attempt.cbt_exam

        exam_questions = list(
            exam.exam_questions
            .select_related(
                "question_version",
            )
            .prefetch_related(
                "question_version__options",
            )
            .order_by("order")
        )

        if not exam_questions:
            raise ValidationError(
                "This CBT exam does not contain any questions."
            )

        if exam.shuffle_questions:
            _rng.shuffle(exam_questions)

        attempt_questions = []

        for display_order, exam_question in enumerate(
            exam_questions,
            start=1,
        ):
            attempt_questions.append(
                AttemptQuestion(
                    attempt=attempt,
                    exam_question=exam_question,
                    display_order=display_order,
                )
            )

        AttemptQuestion.objects.bulk_create(
            attempt_questions
        )

        created_attempt_questions = list(
            attempt.attempt_questions
            .select_related(
                "exam_question",
                "exam_question__question_version",
            )
            .prefetch_related(
                "exam_question__question_version__options",
            )
            .order_by("display_order")
        )

        for attempt_question in created_attempt_questions:
            ExamAttemptService._create_option_order(
                attempt_question=attempt_question,
            )

    # =========================================================
    # MATERIALIZE OPTION ORDER
    # =========================================================

    @staticmethod
    def _create_option_order(
        *,
        attempt_question,
    ):
        exam = attempt_question.attempt.cbt_exam

        version = (
            attempt_question
            .exam_question
            .question_version
        )

        if version.question_type not in {
            QuestionType.SINGLE_CHOICE,
            QuestionType.MULTIPLE_CHOICE,
            QuestionType.TRUE_FALSE,
        }:
            return

        options = list(
            version.options.all().order_by("order")
        )

        if exam.shuffle_options:
            _rng.shuffle(options)

        AttemptQuestionOption.objects.bulk_create(
            [
                AttemptQuestionOption(
                    attempt_question=attempt_question,
                    question_option=option,
                    display_order=display_order,
                )
                for display_order, option in enumerate(
                    options,
                    start=1,
                )
            ]
        )

    # =========================================================
    # GET ACTIVE ATTEMPT
    # =========================================================

    @staticmethod
    def get_active_attempt(
        *,
        exam,
        student,
    ):
        attempt = (
            ExamAttempt.objects
            .filter(
                cbt_exam=exam,
                student=student,
                status=ExamAttemptStatus.IN_PROGRESS,
            )
            .first()
        )

        if attempt is None:
            return None

        if ExamAttemptService.is_expired(attempt):
            return ExamAttemptService.refresh_status(
                attempt=attempt
            )

        return attempt

    # =========================================================
    # ENSURE ATTEMPT IS ACTIVE
    # =========================================================

    @staticmethod
    def ensure_in_progress(attempt):
        if attempt.status != ExamAttemptStatus.IN_PROGRESS:
            raise ValidationError(
                "This exam attempt is no longer in progress."
            )

    # =========================================================
    # EXPIRY CHECK
    # =========================================================

    @staticmethod
    def is_expired(attempt):
        return timezone.now() >= attempt.expires_at

    # =========================================================
    # REFRESH ATTEMPT STATUS
    # =========================================================

    @staticmethod
    @transaction.atomic
    def refresh_status(
        *,
        attempt,
    ):
        attempt = (
            ExamAttempt.objects
            .select_for_update()
            .select_related(
                "cbt_exam",
            )
            .get(pk=attempt.pk)
        )

        if (
            attempt.status
            != ExamAttemptStatus.IN_PROGRESS
        ):
            return attempt

        if not ExamAttemptService.is_expired(attempt):
            return attempt

        return ExamAttemptService._handle_expiry(
            attempt=attempt
        )

    # =========================================================
    # MANUAL SUBMISSION
    # =========================================================

    @staticmethod
    @transaction.atomic
    def submit(
        *,
        attempt,
    ):
        attempt = (
            ExamAttempt.objects
            .select_for_update()
            .select_related(
                "cbt_exam",
            )
            .get(pk=attempt.pk)
        )

        # Idempotent submission.
        if (
            attempt.status
            == ExamAttemptStatus.SUBMITTED
        ):
            return attempt

        if (
            attempt.status
            == ExamAttemptStatus.EXPIRED
        ):
            raise ValidationError(
                "This exam attempt has expired."
            )

        if (
            attempt.status
            != ExamAttemptStatus.IN_PROGRESS
        ):
            raise ValidationError(
                "This exam attempt cannot be submitted."
            )

        if ExamAttemptService.is_expired(attempt):
            return ExamAttemptService._handle_expiry(
                attempt=attempt
            )

        now = timezone.now()

        attempt.status = ExamAttemptStatus.SUBMITTED
        attempt.submitted_at = now
        attempt.last_activity_at = now

        attempt.save(
            update_fields=[
                "status",
                "submitted_at",
                "last_activity_at",
                "updated_at",
            ]
        )

        return attempt

    # =========================================================
    # HANDLE EXPIRY
    # =========================================================

    @staticmethod
    def _handle_expiry(
        *,
        attempt,
    ):
        if (
            attempt.status
            != ExamAttemptStatus.IN_PROGRESS
        ):
            return attempt

        exam = attempt.cbt_exam
        now = timezone.now()

        if exam.auto_submit:
            attempt.status = (
                ExamAttemptStatus.SUBMITTED
            )

            attempt.submitted_at = now

        else:
            attempt.status = (
                ExamAttemptStatus.EXPIRED
            )

            attempt.submitted_at = None

        attempt.last_activity_at = now

        attempt.save(
            update_fields=[
                "status",
                "submitted_at",
                "last_activity_at",
                "updated_at",
            ]
        )

        return attempt

    # =========================================================
    # TOUCH ACTIVITY
    # =========================================================

    @staticmethod
    def touch_activity(
        *,
        attempt,
    ):
        if (
            attempt.status
            != ExamAttemptStatus.IN_PROGRESS
        ):
            return

        attempt.last_activity_at = timezone.now()

        attempt.save(
            update_fields=[
                "last_activity_at",
                "updated_at",
            ]
        )