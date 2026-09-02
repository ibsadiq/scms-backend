from decimal import Decimal, InvalidOperation
from dataclasses import dataclass
import hashlib
import json
import uuid

from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

from ..models import (
    ExamAttemptStatus,
    QuestionType,
    StudentAnswer,
    StudentChoiceAnswer,
    StudentTextAnswer,
    StudentNumericAnswer,
    StudentFillBlankAnswer,
    StudentMatchingAnswer,
    AttemptMatchingItem,
    AttemptQuestion,
    ExamAttempt,
    AttemptAnswerEvent,
    AttemptQuestionClientState,
    AnswerEventOrigin,
)


@dataclass(frozen=True)
class AnswerEventResult:
    event: AttemptAnswerEvent
    answer: StudentAnswer | None
    outcome: str
    replayed: bool = False


class StudentAnswerService:

    @staticmethod
    def _json_safe(value):
        if isinstance(value, dict):
            return {
                str(key): StudentAnswerService._json_safe(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [StudentAnswerService._json_safe(item) for item in value]
        if isinstance(value, (uuid.UUID, Decimal)):
            return str(value)
        return value

    @staticmethod
    def _payload_hash(payload):
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    @transaction.atomic
    def apply_answer_event(
        *,
        attempt_question,
        operation,
        payload=None,
        event_id=None,
        client_id=None,
        client_sequence=None,
        base_revision=None,
        client_timestamp=None,
        student=None,
        origin=AnswerEventOrigin.ONLINE,
    ):
        """Apply one answer command under the attempt serialization lock.

        Lock order is always ExamAttempt, then AttemptQuestion. Sequence
        ordering is scoped to (attempt question, client), so unrelated
        questions and future clients do not make each other stale.
        """
        preliminary_attempt_id = attempt_question.attempt_id
        attempt = ExamAttempt.objects.select_for_update().get(
            pk=preliminary_attempt_id
        )
        if student is not None and attempt.student_id != student.pk:
            raise ValidationError("This attempt does not belong to the student.")
        locked_question = (
            AttemptQuestion.objects.select_for_update()
            .select_related("attempt")
            .get(pk=attempt_question.pk, attempt_id=attempt.pk)
        )

        event_id = event_id or uuid.uuid4()
        client_id = client_id or uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"ssync:legacy-cbt-client:{attempt.public_id}",
        )
        payload = StudentAnswerService._json_safe(payload or {})
        payload_hash = StudentAnswerService._payload_hash(payload)

        existing = AttemptAnswerEvent.objects.filter(
            attempt=attempt,
            event_id=event_id,
        ).first()
        if existing:
            same_command = (
                existing.attempt_question_id == locked_question.id
                and existing.client_id == client_id
                and existing.client_sequence == client_sequence
                and existing.operation == operation
                and existing.payload_hash == payload_hash
                and existing.base_revision == base_revision
            )
            if not same_command:
                raise ValidationError(
                    "This event identifier was already used for a different answer operation."
                )
            return AnswerEventResult(
                event=existing,
                answer=getattr(locked_question, "answer", None),
                outcome="DUPLICATE",
                replayed=True,
            )

        occurrence_time = (
            client_timestamp if origin == AnswerEventOrigin.OFFLINE_SYNC else timezone.now()
        )
        StudentAnswerService.ensure_answerable(
            locked_question,
            occurrence_time=occurrence_time,
            allow_delayed_upload=(origin == AnswerEventOrigin.OFFLINE_SYNC),
        )

        state, _ = AttemptQuestionClientState.objects.select_for_update().get_or_create(
            attempt_question=locked_question,
            client_id=client_id,
        )
        if client_sequence is None:
            client_sequence = state.last_client_sequence + 1
        if client_sequence <= 0:
            raise ValidationError("Client sequence must be greater than zero.")

        sequence_event = AttemptAnswerEvent.objects.filter(
            attempt_question=locked_question,
            client_id=client_id,
            client_sequence=client_sequence,
        ).first()
        if sequence_event:
            raise ValidationError(
                "This client sequence was already used for another answer operation."
            )

        if client_sequence <= state.last_client_sequence:
            event = AttemptAnswerEvent.objects.create(
                event_id=event_id,
                attempt=attempt,
                attempt_question=locked_question,
                client_id=client_id,
                client_sequence=client_sequence,
                base_revision=base_revision,
                operation=operation,
                payload=payload,
                payload_hash=payload_hash,
                outcome=AttemptAnswerEvent.Outcome.STALE,
                server_revision=attempt.revision,
                client_timestamp=client_timestamp,
                origin=origin,
            )
            return AnswerEventResult(
                event=event,
                answer=getattr(locked_question, "answer", None),
                outcome=AttemptAnswerEvent.Outcome.STALE,
            )

        if operation == AttemptAnswerEvent.Operation.CLEAR:
            answer = StudentAnswerService.clear_answer(
                attempt_question=locked_question,
                enforce_window=False,
            )
        elif operation == AttemptAnswerEvent.Operation.SET:
            answer = StudentAnswerService._apply_set_payload(
                attempt_question=locked_question,
                payload=payload,
                enforce_window=False,
            )
        else:
            raise ValidationError("Unsupported answer event operation.")

        attempt.revision += 1
        attempt.last_activity_at = timezone.now()
        attempt.save(update_fields=["revision", "last_activity_at", "updated_at"])

        state.last_client_sequence = client_sequence
        state.last_server_revision = attempt.revision
        state.save(update_fields=[
            "last_client_sequence", "last_server_revision", "updated_at"
        ])
        event = AttemptAnswerEvent.objects.create(
            event_id=event_id,
            attempt=attempt,
            attempt_question=locked_question,
            client_id=client_id,
            client_sequence=client_sequence,
            base_revision=base_revision,
            operation=operation,
            payload=payload,
            payload_hash=payload_hash,
            outcome=AttemptAnswerEvent.Outcome.ACCEPTED,
            server_revision=attempt.revision,
            client_timestamp=client_timestamp,
            accepted_at=timezone.now(),
            origin=origin,
        )
        return AnswerEventResult(
            event=event,
            answer=answer,
            outcome=AttemptAnswerEvent.Outcome.ACCEPTED,
        )

    @staticmethod
    def _apply_set_payload(*, attempt_question, payload, enforce_window=True):
        q_type = StudentAnswerService._get_question_type(attempt_question)
        if q_type in {
            QuestionType.SINGLE_CHOICE,
            QuestionType.MULTIPLE_CHOICE,
            QuestionType.TRUE_FALSE,
        }:
            return StudentAnswerService.save_choice_answer(
                attempt_question=attempt_question,
                option_ids=payload.get("option_ids", []),
                enforce_window=enforce_window,
            )
        if q_type in {QuestionType.SHORT_ANSWER, QuestionType.ESSAY}:
            return StudentAnswerService.save_text_answer(
                attempt_question=attempt_question,
                text=payload.get("text", ""),
                enforce_window=enforce_window,
            )
        if q_type == QuestionType.NUMERIC:
            return StudentAnswerService.save_numeric_answer(
                attempt_question=attempt_question,
                value=payload.get("value", ""),
                enforce_window=enforce_window,
            )
        if q_type == QuestionType.FILL_BLANK:
            return StudentAnswerService.save_fill_blank_answer(
                attempt_question=attempt_question,
                responses=payload.get("responses", {}),
                enforce_window=enforce_window,
            )
        if q_type == QuestionType.MATCHING:
            return StudentAnswerService.save_matching_answer(
                attempt_question=attempt_question,
                matches=payload.get("matches", {}),
                enforce_window=enforce_window,
            )
        raise ValidationError(f"Unsupported question type: {q_type}")

    # =========================================================
    # COMMON HELPERS
    # =========================================================

    @staticmethod
    def ensure_answerable(
        attempt_question, *, occurrence_time=None, allow_delayed_upload=False
    ):
        attempt = attempt_question.attempt

        if attempt.status != ExamAttemptStatus.IN_PROGRESS:
            raise ValidationError(
                "Answers can only be changed while "
                "the attempt is in progress."
            )

        check_time = occurrence_time or timezone.now()
        if timezone.is_naive(check_time):
            raise ValidationError("Answer event timestamp must include a timezone.")
        if allow_delayed_upload and check_time < attempt.started_at:
            raise ValidationError("Answer event occurred before the attempt started.")
        if check_time >= attempt.expires_at:
            raise ValidationError(
                "This exam attempt has expired."
            )

    @staticmethod
    def _get_version(attempt_question):
        return (
            attempt_question
            .exam_question
            .question_version
        )

    @staticmethod
    def _get_question_type(attempt_question):
        if attempt_question.published_question_id:
            return attempt_question.published_question.question_type
        return StudentAnswerService._get_version(attempt_question).question_type

    @staticmethod
    def _get_answer(attempt_question):
        answer, _ = StudentAnswer.objects.get_or_create(
            attempt_question=attempt_question
        )

        return answer

    @staticmethod
    def _set_answer_state(
        *,
        answer,
        is_answered,
    ):
        answer.is_answered = is_answered

        answer.answered_at = (
            timezone.now()
            if is_answered
            else None
        )

        answer.save(
            update_fields=[
                "is_answered",
                "answered_at",
                "updated_at",
            ]
        )

        StudentAnswerService._touch_attempt(
            answer.attempt_question.attempt
        )

    @staticmethod
    def _touch_attempt(attempt):
        attempt.last_activity_at = timezone.now()

        attempt.save(
            update_fields=[
                "last_activity_at",
                "updated_at",
            ]
        )

    # =========================================================
    # CHOICE ANSWERS
    # SINGLE_CHOICE
    # MULTIPLE_CHOICE
    # TRUE_FALSE
    # =========================================================

    @staticmethod
    @transaction.atomic
    def save_choice_answer(
        *,
        attempt_question,
        option_ids,
        enforce_window=True,
    ):
        if enforce_window:
            StudentAnswerService.ensure_answerable(attempt_question)

        question_type = StudentAnswerService._get_question_type(attempt_question)
        if question_type not in {
            QuestionType.SINGLE_CHOICE,
            QuestionType.MULTIPLE_CHOICE,
            QuestionType.TRUE_FALSE,
        }:
            raise ValidationError(
                "This question does not accept option answers."
            )

        option_ids = list(
            dict.fromkeys(option_ids or [])
        )

        if attempt_question.published_question_id:
            try:
                normalized_ids = [uuid.UUID(str(value)) for value in option_ids]
            except (TypeError, ValueError, AttributeError):
                raise ValidationError("One or more selected options are invalid.")
            options = list(attempt_question.published_question.choices.filter(
                public_id__in=normalized_ids
            ))
        else:
            try:
                normalized_ids = [int(value) for value in option_ids]
            except (TypeError, ValueError):
                raise ValidationError("One or more selected options are invalid.")
            options = list(StudentAnswerService._get_version(
                attempt_question
            ).options.filter(id__in=normalized_ids))

        if len(options) != len(option_ids):
            raise ValidationError(
                "One or more selected options are invalid."
            )

        if (
            question_type
            in {
                QuestionType.SINGLE_CHOICE,
                QuestionType.TRUE_FALSE,
            }
            and len(options) > 1
        ):
            raise ValidationError(
                "Only one option may be selected."
            )

        answer = StudentAnswerService._get_answer(
            attempt_question
        )

        # Replace existing selection.
        answer.selected_options.all().delete()

        StudentChoiceAnswer.objects.bulk_create(
            [
                StudentChoiceAnswer(
                    student_answer=answer,
                    published_choice=(option if attempt_question.published_question_id else None),
                    question_option=(None if attempt_question.published_question_id else option),
                )
                for option in options
            ]
        )

        StudentAnswerService._set_answer_state(
            answer=answer,
            is_answered=bool(options),
        )

        return answer

    # =========================================================
    # TEXT ANSWERS
    # SHORT_ANSWER
    # ESSAY
    # =========================================================

    @staticmethod
    @transaction.atomic
    def save_text_answer(
        *,
        attempt_question,
        text,
        enforce_window=True,
    ):
        if enforce_window:
            StudentAnswerService.ensure_answerable(attempt_question)

        if StudentAnswerService._get_question_type(attempt_question) not in {
            QuestionType.SHORT_ANSWER,
            QuestionType.ESSAY,
        }:
            raise ValidationError(
                "This question does not accept a text answer."
            )

        text = text or ""

        answer = StudentAnswerService._get_answer(
            attempt_question
        )

        if not text.strip():
            StudentTextAnswer.objects.filter(
                student_answer=answer
            ).delete()

            StudentAnswerService._set_answer_state(
                answer=answer,
                is_answered=False,
            )

            return answer

        StudentTextAnswer.objects.update_or_create(
            student_answer=answer,
            defaults={
                "text": text,
            },
        )

        StudentAnswerService._set_answer_state(
            answer=answer,
            is_answered=True,
        )

        return answer

    # =========================================================
    # NUMERIC
    # =========================================================

    @staticmethod
    @transaction.atomic
    def save_numeric_answer(
        *,
        attempt_question,
        value,
        enforce_window=True,
    ):
        if enforce_window:
            StudentAnswerService.ensure_answerable(attempt_question)

        if StudentAnswerService._get_question_type(attempt_question) != QuestionType.NUMERIC:
            raise ValidationError(
                "This question does not accept "
                "a numeric answer."
            )

        answer = StudentAnswerService._get_answer(
            attempt_question
        )

        # Empty value means clear the response.
        if value is None or value == "":
            StudentNumericAnswer.objects.filter(
                student_answer=answer
            ).delete()

            StudentAnswerService._set_answer_state(
                answer=answer,
                is_answered=False,
            )

            return answer

        try:
            numeric_value = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError(
                "A valid numeric value is required."
            )

        StudentNumericAnswer.objects.update_or_create(
            student_answer=answer,
            defaults={
                "value": numeric_value,
            },
        )

        StudentAnswerService._set_answer_state(
            answer=answer,
            is_answered=True,
        )

        return answer

    # =========================================================
    # FILL IN THE BLANK
    #
    # Expected input:
    #
    # responses = {
    #     blank_id: "answer",
    #     blank_id: "answer",
    # }
    #
    # =========================================================

    @staticmethod
    @transaction.atomic
    def save_fill_blank_answer(
        *,
        attempt_question,
        responses,
        enforce_window=True,
    ):
        if enforce_window:
            StudentAnswerService.ensure_answerable(attempt_question)

        if StudentAnswerService._get_question_type(attempt_question) != QuestionType.FILL_BLANK:
            raise ValidationError(
                "This question does not accept "
                "fill-in-the-blank answers."
            )

        responses = responses or {}
        if attempt_question.published_question_id:
            try:
                submitted_blank_ids = {uuid.UUID(str(value)) for value in responses}
            except (TypeError, ValueError, AttributeError):
                raise ValidationError("One or more blank IDs are invalid.")
            valid_blanks = {
                str(blank.public_id): blank
                for blank in attempt_question.published_question.blanks.filter(
                    public_id__in=submitted_blank_ids
                )
            }
        else:
            version = StudentAnswerService._get_version(attempt_question)
            try:
                definition = version.fill_blank_definition
            except ObjectDoesNotExist:
                raise ValidationError(
                    "This question does not have a fill-in-the-blank definition."
                )
            try:
                submitted_blank_ids = {int(blank_id) for blank_id in responses}
            except (TypeError, ValueError):
                raise ValidationError("One or more blank IDs are invalid.")
            valid_blanks = {
                str(blank.id): blank
                for blank in definition.blanks.filter(id__in=submitted_blank_ids)
            }

        if len(valid_blanks) != len(
            submitted_blank_ids
        ):
            raise ValidationError(
                "One or more blanks do not belong "
                "to this question."
            )

        answer = StudentAnswerService._get_answer(
            attempt_question
        )

        # Replace the current response set.
        answer.blank_responses.all().delete()

        response_objects = []

        for raw_blank_id, value in responses.items():
            blank_id = str(raw_blank_id)

            value = (
                str(value)
                if value is not None
                else ""
            )

            # Empty blanks are simply unanswered.
            if not value.strip():
                continue

            response_objects.append(
                StudentFillBlankAnswer(
                    student_answer=answer,
                    published_blank=(valid_blanks[blank_id] if attempt_question.published_question_id else None),
                    blank=(None if attempt_question.published_question_id else valid_blanks[blank_id]),
                    answer=value,
                )
            )

        StudentFillBlankAnswer.objects.bulk_create(
            response_objects
        )

        StudentAnswerService._set_answer_state(
            answer=answer,
            is_answered=bool(response_objects),
        )

        return answer

    # =========================================================
    # MATCHING
    #
    # Expected input:
    #
    # matches = {
    #     opaque_left_id: opaque_right_id,
    # }
    #
    # =========================================================

    @staticmethod
    @transaction.atomic
    def save_matching_answer(
        *,
        attempt_question,
        matches,
        enforce_window=True,
    ):
        if enforce_window:
            StudentAnswerService.ensure_answerable(attempt_question)

        if StudentAnswerService._get_question_type(attempt_question) != QuestionType.MATCHING:
            raise ValidationError(
                "This question does not accept "
                "matching answers."
            )

        matches = matches or {}

        try:
            left_public_ids = {uuid.UUID(str(item)) for item in matches.keys()}
            right_public_ids = {
                uuid.UUID(str(item))
                for item in matches.values()
                if item not in {None, ""}
            }
        except (TypeError, ValueError, AttributeError):
            raise ValidationError(
                "One or more matching item IDs are invalid."
            )

        presentation = list(
            AttemptMatchingItem.objects.filter(
                attempt_question=attempt_question,
            ).select_related("matching_pair", "published_item")
        )
        by_public_id = {
            (item.published_item.public_id if item.published_item_id else item.public_id): item
            for item in presentation
        }
        if set(by_public_id) != left_public_ids | right_public_ids:
            raise ValidationError(
                "One or more matching items do not "
                "belong to this question."
            )

        if any(by_public_id[item].side != AttemptMatchingItem.Side.LEFT for item in left_public_ids):
            raise ValidationError("A right-side item cannot be used as a left-side item.")
        if any(by_public_id[item].side != AttemptMatchingItem.Side.RIGHT for item in right_public_ids):
            raise ValidationError("A left-side item cannot be used as a right-side item.")

        answer = StudentAnswerService._get_answer(
            attempt_question
        )

        answer.matching_responses.all().delete()

        response_objects = []

        selected_right_ids = set()

        for raw_left_id, raw_right_id in matches.items():
            left_item = by_public_id[uuid.UUID(str(raw_left_id))]

            # Allow clearing/unmatched left items.
            if raw_right_id in {
                None,
                "",
            }:
                continue

            right_public_id = uuid.UUID(str(raw_right_id))

            if right_public_id in selected_right_ids:
                raise ValidationError(
                    "The same right-side item cannot "
                    "be matched more than once."
                )

            selected_right_ids.add(right_public_id)
            right_item = by_public_id[right_public_id]

            response_objects.append(
                StudentMatchingAnswer(
                    student_answer=answer,
                    published_left_item=(left_item.published_item if left_item.published_item_id else None),
                    published_right_item=(right_item.published_item if right_item.published_item_id else None),
                    left_pair=(None if left_item.published_item_id else left_item.matching_pair),
                    selected_right_pair=(None if right_item.published_item_id else right_item.matching_pair),
                )
            )

        StudentMatchingAnswer.objects.bulk_create(
            response_objects
        )

        StudentAnswerService._set_answer_state(
            answer=answer,
            is_answered=bool(response_objects),
        )

        return answer

    # =========================================================
    # CLEAR ANSWER
    # =========================================================

    @staticmethod
    @transaction.atomic
    def clear_answer(
        *,
        attempt_question,
        enforce_window=True,
    ):
        if enforce_window:
            StudentAnswerService.ensure_answerable(attempt_question)

        try:
            answer = attempt_question.answer
        except StudentAnswer.DoesNotExist:
            StudentAnswerService._touch_attempt(
                attempt_question.attempt
            )
            return None

        # Choice
        answer.selected_options.all().delete()

        # Text
        StudentTextAnswer.objects.filter(
            student_answer=answer
        ).delete()

        # Numeric
        StudentNumericAnswer.objects.filter(
            student_answer=answer
        ).delete()

        # Fill blank
        answer.blank_responses.all().delete()

        # Matching
        answer.matching_responses.all().delete()

        answer.is_answered = False
        answer.answered_at = None

        answer.save(
            update_fields=[
                "is_answered",
                "answered_at",
                "updated_at",
            ]
        )

        StudentAnswerService._touch_attempt(
            attempt_question.attempt
        )

        return answer

    # =========================================================
    # FLAG / UNFLAG
    #
    # Flagging belongs to AttemptQuestion,
    # not StudentAnswer.
    # =========================================================

    @staticmethod
    @transaction.atomic
    def set_flagged(
        *,
        attempt_question,
        flagged,
    ):
        StudentAnswerService.ensure_answerable(
            attempt_question
        )

        attempt_question.is_flagged = bool(flagged)

        attempt_question.save(
            update_fields=[
                "is_flagged",
            ]
        )

        StudentAnswerService._touch_attempt(
            attempt_question.attempt
        )

        return attempt_question
