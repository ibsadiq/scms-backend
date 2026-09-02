import secrets
from dataclasses import dataclass
from datetime import timedelta
import hashlib
import json
import uuid

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import (
    CBTExam,
    CBTExamStatus,
    ExamAttempt,
    ExamAttemptStatus,
    AttemptQuestion,
    AttemptQuestionOption,
    AttemptMatchingItem,
    QuestionType,
    PublishedExamChoice,
    PublishedExamMatchingItem,
    AttemptExpiryPolicy,
    AttemptGrantStatus,
)
from .published_exam_revision_service import PublishedExamRevisionService
from .exam_access_service import CBTExamAccessService, ExamAccessState
from .attempt_grant_service import AttemptGrantService


_rng = secrets.SystemRandom()


@dataclass(frozen=True)
class SubmissionResult:
    attempt: ExamAttempt
    outcome: str
    finalized_now: bool


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
        now=None,
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
        now = now or timezone.now()

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
                existing_attempt.attempt_grant_id
                and existing_attempt.attempt_grant.status == AttemptGrantStatus.REVOKED
            ):
                raise ValidationError("Your attempt authorization has been revoked.")
            if (
                existing_attempt.status
                == ExamAttemptStatus.IN_PROGRESS
            ):
                if now >= existing_attempt.expires_at:
                    return (
                        ExamAttemptService
                        ._handle_expiry(
                            attempt=existing_attempt
                        )
                    )
                return existing_attempt

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

        if not exam.exam_questions.exists():
            raise ValidationError(
                "This CBT exam does not contain any questions."
            )

        published_revision = PublishedExamRevisionService.ensure_current_for_exam(exam)
        access = CBTExamAccessService.evaluate(
            student=student,
            exam=exam,
            now=now,
            attempt=None,
            revision=published_revision,
        )
        if access.state != ExamAccessState.AVAILABLE:
            raise ValidationError(access.message)
        enrollment = access.enrollment
        grant = AttemptGrantService.issue(
            student=student,
            exam=exam,
            revision=published_revision,
            now=now,
            exam_locked=True,
        )

        started_at = now

        expires_at = (
            started_at
            + timedelta(
                minutes=published_revision.duration_minutes
            )
        )
        if (
            exam.attempt_expiry_policy == AttemptExpiryPolicy.CAP_AT_EXAM_CLOSE
            and exam.available_until is not None
        ):
            expires_at = min(expires_at, exam.available_until)

        attempt = ExamAttempt.objects.create(
            cbt_exam=exam,
            student=student,
            enrollment=enrollment,
            status=ExamAttemptStatus.IN_PROGRESS,
            started_at=started_at,
            expires_at=expires_at,
            last_activity_at=started_at,
            published_revision=published_revision,
            attempt_grant=grant,
        )

        grant.status = AttemptGrantStatus.CONSUMED
        grant.save(update_fields=["status", "updated_at"])

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

        if attempt.published_revision_id:
            published_questions = list(
                attempt.published_revision.questions.prefetch_related(
                    "choices", "matching_items"
                ).order_by("order")
            )
            if attempt.published_revision.shuffle_questions:
                _rng.shuffle(published_questions)
            AttemptQuestion.objects.bulk_create([
                AttemptQuestion(
                    attempt=attempt,
                    published_question=question,
                    display_order=display_order,
                )
                for display_order, question in enumerate(published_questions, 1)
            ])
            created = list(
                attempt.attempt_questions.select_related("published_question")
                .prefetch_related(
                    "published_question__choices",
                    "published_question__matching_items",
                ).order_by("display_order")
            )
            for attempt_question in created:
                ExamAttemptService._create_option_order(attempt_question=attempt_question)
                ExamAttemptService._create_matching_order(attempt_question=attempt_question)
            return

        exam_questions = list(
            exam.exam_questions
            .select_related(
                "question_version",
            )
            .prefetch_related(
                "question_version__options",
                "question_version__matching_definition__pairs",
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
                "exam_question__question_version__matching_definition__pairs",
            )
            .order_by("display_order")
        )

        for attempt_question in created_attempt_questions:
            ExamAttemptService._create_option_order(
                attempt_question=attempt_question,
            )
            ExamAttemptService._create_matching_order(
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

        if attempt_question.published_question_id:
            question = attempt_question.published_question
            if question.question_type not in {
                QuestionType.SINGLE_CHOICE,
                QuestionType.MULTIPLE_CHOICE,
                QuestionType.TRUE_FALSE,
            }:
                return
            choices = list(question.choices.all().order_by("order"))
            if attempt_question.attempt.published_revision.shuffle_options:
                _rng.shuffle(choices)
            AttemptQuestionOption.objects.bulk_create([
                AttemptQuestionOption(
                    attempt_question=attempt_question,
                    published_choice=choice,
                    display_order=display_order,
                )
                for display_order, choice in enumerate(choices, 1)
            ])
            return

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

    @staticmethod
    def _create_matching_order(*, attempt_question):
        if attempt_question.published_question_id:
            question = attempt_question.published_question
            if question.question_type != QuestionType.MATCHING:
                return
            left = list(question.matching_items.filter(side="LEFT").order_by("order"))
            right = list(question.matching_items.filter(side="RIGHT").order_by("order"))
            if question.interaction_config.get("shuffle_right_items", True):
                _rng.shuffle(right)
            else:
                right.sort(key=lambda item: (item.text.casefold(), item.pk))
            AttemptMatchingItem.objects.bulk_create([
                AttemptMatchingItem(
                    attempt_question=attempt_question,
                    published_item=item,
                    side=AttemptMatchingItem.Side.LEFT,
                    display_order=order,
                )
                for order, item in enumerate(left, 1)
            ] + [
                AttemptMatchingItem(
                    attempt_question=attempt_question,
                    published_item=item,
                    side=AttemptMatchingItem.Side.RIGHT,
                    display_order=order,
                )
                for order, item in enumerate(right, 1)
            ])
            return
        version = attempt_question.exam_question.question_version
        if version.question_type != QuestionType.MATCHING:
            return

        definition = version.matching_definition
        pairs = list(definition.pairs.all().order_by("order"))
        right_pairs = list(pairs)
        if definition.shuffle_right_items:
            _rng.shuffle(right_pairs)
        else:
            right_pairs.sort(key=lambda pair: (pair.right_text.casefold(), pair.pk))

        AttemptMatchingItem.objects.bulk_create(
            [
                AttemptMatchingItem(
                    attempt_question=attempt_question,
                    matching_pair=pair,
                    side=AttemptMatchingItem.Side.LEFT,
                    display_order=order,
                )
                for order, pair in enumerate(pairs, start=1)
            ]
            + [
                AttemptMatchingItem(
                    attempt_question=attempt_question,
                    matching_pair=pair,
                    side=AttemptMatchingItem.Side.RIGHT,
                    display_order=order,
                )
                for order, pair in enumerate(right_pairs, start=1)
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
        submission_id=None,
        allow_expired_reconciliation=False,
        client_submitted_at=None,
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
            outcome = (
                "DUPLICATE"
                if submission_id and attempt.submission_id == submission_id
                else "ALREADY_SUBMITTED"
            )
            return SubmissionResult(attempt, outcome, False)

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

        delayed_submission_is_valid = (
            allow_expired_reconciliation
            and client_submitted_at is not None
            and attempt.started_at <= client_submitted_at < attempt.expires_at
        )
        if ExamAttemptService.is_expired(attempt) and not delayed_submission_is_valid:
            expired_attempt = ExamAttemptService._handle_expiry(
                attempt=attempt
            )
            return SubmissionResult(
                expired_attempt,
                "ACCEPTED" if expired_attempt.status == ExamAttemptStatus.SUBMITTED else "EXPIRED",
                expired_attempt.status == ExamAttemptStatus.SUBMITTED,
            )

        now = timezone.now()
        submission_id = submission_id or uuid.uuid4()

        attempt.status = ExamAttemptStatus.SUBMITTED
        attempt.submission_id = submission_id
        attempt.submitted_revision = attempt.revision
        attempt.submission_snapshot_hash = ExamAttemptService._snapshot_hash(attempt)
        attempt.submitted_at = now
        if client_submitted_at is not None:
            attempt.client_reported_submitted_at = client_submitted_at
        attempt.last_activity_at = now

        attempt.save(
            update_fields=[
                "status",
                "submission_id",
                "submitted_revision",
                "submission_snapshot_hash",
                "submitted_at",
                "client_reported_submitted_at",
                "last_activity_at",
                "updated_at",
            ]
        )

        return SubmissionResult(attempt, "ACCEPTED", True)

    @staticmethod
    def _snapshot_hash(attempt):
        questions = []
        attempt_questions = (
            attempt.attempt_questions
            .select_related("exam_question__question_version", "published_question", "answer")
            .prefetch_related(
                "answer__selected_options__published_choice",
                "answer__blank_responses__published_blank",
                "answer__matching_responses__published_left_item",
                "answer__matching_responses__published_right_item",
            )
            .order_by("display_order")
        )
        for question in attempt_questions:
            answer = getattr(question, "answer", None)
            response = None
            if answer and answer.is_answered:
                q_type = (
                    question.published_question.question_type
                    if question.published_question_id
                    else question.exam_question.question_version.question_type
                )
                if q_type in {
                    QuestionType.SINGLE_CHOICE,
                    QuestionType.MULTIPLE_CHOICE,
                    QuestionType.TRUE_FALSE,
                }:
                    response = {"option_ids": sorted(
                        str(item.published_choice.public_id) if item.published_choice_id else str(item.question_option_id)
                        for item in answer.selected_options.all()
                    )}
                elif q_type in {QuestionType.SHORT_ANSWER, QuestionType.ESSAY}:
                    response = {"text": answer.text_response.text}
                elif q_type == QuestionType.NUMERIC:
                    response = {"value": str(answer.numeric_response.value)}
                elif q_type == QuestionType.FILL_BLANK:
                    response = {
                        "responses": {
                            (str(item.published_blank.public_id) if item.published_blank_id else str(item.blank_id)): item.answer
                            for item in answer.blank_responses.all()
                        }
                    }
                elif q_type == QuestionType.MATCHING:
                    response = {
                        "matches": {
                            (str(item.published_left_item.public_id) if item.published_left_item_id else str(item.left_pair_id)):
                            (str(item.published_right_item.public_id) if item.published_right_item_id else str(item.selected_right_pair_id))
                            for item in answer.matching_responses.all()
                        }
                    }
            questions.append({
                "attempt_question": str(question.public_id),
                "response": response,
            })
        canonical = {
            "attempt": str(attempt.public_id),
            "revision": attempt.revision,
            "questions": questions,
        }
        encoded = json.dumps(
            canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

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

        auto_submit = (
            attempt.published_revision.auto_submit
            if attempt.published_revision_id
            else exam.auto_submit
        )
        if auto_submit:
            attempt.status = (
                ExamAttemptStatus.SUBMITTED
            )

            attempt.submitted_at = now
            attempt.submission_id = attempt.submission_id or uuid.uuid4()
            attempt.submitted_revision = attempt.revision
            attempt.submission_snapshot_hash = ExamAttemptService._snapshot_hash(attempt)

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
                "submission_id",
                "submitted_revision",
                "submission_snapshot_hash",
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
