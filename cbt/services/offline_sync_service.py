from dataclasses import dataclass
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from cbt.models import (
    AnswerEventOrigin,
    AttemptExpiryPolicy,
    AttemptGrantStatus,
    AttemptMatchingItem,
    AttemptQuestion,
    AttemptQuestionOption,
    AttemptStartSource,
    CBTExam,
    ExamAttempt,
    ExamAttemptStatus,
    OfflineExamPackage,
    PublishedExamChoice,
    PublishedExamMatchingItem,
    PublishedExamQuestion,
)
from academic.models import StudentClassEnrollment
from .attempt_grant_service import AttemptGrantService
from .exam_attempt_service import ExamAttemptService
from .offline_package_service import OfflinePackageError, OfflinePackageService
from .student_answer_service import StudentAnswerService


class OfflineSyncError(ValidationError):
    def __init__(self, message, *, code):
        self.sync_code = code
        super().__init__(message, code=code)


@dataclass(frozen=True)
class OfflineSyncResult:
    attempt: ExamAttempt
    events: list


class OfflineSyncService:
    PROTOCOL_VERSION = 1
    MAX_BATCH_EVENTS = 100
    MAX_START_CLOCK_SKEW_SECONDS = getattr(
        settings, "CBT_OFFLINE_START_CLOCK_SKEW_SECONDS", 300
    )

    @staticmethod
    def _verify_protocol(version):
        if version != OfflineSyncService.PROTOCOL_VERSION:
            raise OfflineSyncError(
                "Unsupported offline sync protocol.", code="UNSUPPORTED_SYNC_VERSION"
            )

    @staticmethod
    def _verify_package_credentials(
        *, package, student, package_hash, package_signature, grant_token,
        allow_expired_grant=True,
    ):
        if package_hash != package.package_hash:
            raise OfflineSyncError("Package hash does not match.", code="PACKAGE_INTEGRITY_ERROR")
        try:
            OfflinePackageService.verify(
                package=package, student=student, signature=package_signature
            )
        except OfflinePackageError as exc:
            raise OfflineSyncError(exc.messages, code=exc.package_code) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise OfflineSyncError(
                "Package content is invalid.", code="PACKAGE_INTEGRITY_ERROR"
            ) from exc
        try:
            verified = AttemptGrantService.verify_token(
                grant_token,
                expected_student=student,
                allow_before_valid_from=True,
                allow_after_valid_until=allow_expired_grant,
            )
        except ValidationError as exc:
            message = " ".join(getattr(exc, "messages", [])).casefold()
            code = "GRANT_REVOKED" if "revoked" in message else "INVALID_GRANT"
            raise OfflineSyncError("Grant authorization is invalid.", code=code) from exc
        grant = verified.grant
        if grant.pk != package.attempt_grant_id:
            raise OfflineSyncError("Grant does not belong to this package.", code="PACKAGE_MISMATCH")
        if (
            grant.student_id != package.student_id
            or grant.exam_id != package.exam_id
            or grant.published_revision_id != package.published_revision_id
        ):
            raise OfflineSyncError("Package provenance is inconsistent.", code="PACKAGE_MISMATCH")
        return grant

    @staticmethod
    @transaction.atomic
    def bootstrap(
        *, student, package_id, package_hash, package_signature, grant_token,
        client_id, offline_started_at, protocol_version=1, now=None,
    ):
        OfflineSyncService._verify_protocol(protocol_version)
        now = now or timezone.now()
        if timezone.is_naive(offline_started_at):
            raise OfflineSyncError("Offline start must include a timezone.", code="INVALID_START_TIME")
        if offline_started_at > now + timedelta(
            seconds=OfflineSyncService.MAX_START_CLOCK_SKEW_SECONDS
        ):
            raise OfflineSyncError(
                "Reported offline start is ahead of server reconciliation time.",
                code="INVALID_START_TIME",
            )
        try:
            package_ref = OfflineExamPackage.objects.select_related("exam").get(
                public_id=package_id, student=student
            )
        except OfflineExamPackage.DoesNotExist as exc:
            raise OfflineSyncError("Offline package was not found.", code="PACKAGE_NOT_FOUND") from exc

        # Shared lock order: exam -> grant -> package -> attempt.
        exam = CBTExam.objects.select_for_update().get(pk=package_ref.exam_id)
        grant_model = package_ref.attempt_grant.__class__
        grant = grant_model.objects.select_for_update().select_related(
            "published_revision"
        ).get(pk=package_ref.attempt_grant_id)
        package = OfflineExamPackage.objects.select_for_update().select_related(
            "student", "exam", "published_revision", "attempt_grant"
        ).get(pk=package_ref.pk)
        OfflineSyncService._verify_package_credentials(
            package=package,
            student=student,
            package_hash=package_hash,
            package_signature=package_signature,
            grant_token=grant_token,
        )
        if grant.status == AttemptGrantStatus.REVOKED:
            raise OfflineSyncError("Grant has been revoked.", code="GRANT_REVOKED")

        existing = ExamAttempt.objects.select_for_update().filter(
            cbt_exam=exam, student=student
        ).first()
        if existing:
            if existing.offline_package_id != package.pk:
                raise OfflineSyncError(
                    "An attempt already exists for a different authorization.",
                    code="PACKAGE_MISMATCH",
                )
            return existing

        if not (grant.valid_from <= offline_started_at < grant.valid_until):
            raise OfflineSyncError(
                "Reported offline start is outside the signed grant window.",
                code="START_OUTSIDE_GRANT_WINDOW",
            )
        expires_at = offline_started_at + timedelta(
            minutes=package.published_revision.duration_minutes
        )
        if exam.attempt_expiry_policy == AttemptExpiryPolicy.CAP_AT_EXAM_CLOSE:
            if exam.available_until is not None:
                expires_at = min(expires_at, exam.available_until)
        # A package may authorize a delayed upload, never execution past its grant.
        expires_at = min(expires_at, grant.valid_until)
        if expires_at <= offline_started_at:
            raise OfflineSyncError("Offline attempt has no valid execution window.", code="ATTEMPT_EXPIRED")

        enrollment = StudentClassEnrollment.objects.filter(
            student=student,
            classroom=exam.classroom,
            academic_year=exam.session.academic_year,
            is_active=True,
        ).first()
        if enrollment is None:
            raise OfflineSyncError("Student enrollment is unavailable.", code="INVALID_GRANT")
        try:
            with transaction.atomic():
                attempt = ExamAttempt.objects.create(
                    cbt_exam=exam,
                    student=student,
                    enrollment=enrollment,
                    published_revision=package.published_revision,
                    attempt_grant=grant,
                    offline_package=package,
                    start_source=AttemptStartSource.OFFLINE_RECONCILED,
                    client_reported_started_at=offline_started_at,
                    server_reconciled_at=now,
                    started_at=offline_started_at,
                    expires_at=expires_at,
                    last_activity_at=now,
                )
        except IntegrityError:
            attempt = ExamAttempt.objects.select_for_update().get(
                cbt_exam=exam, student=student
            )
            if attempt.offline_package_id != package.pk:
                raise OfflineSyncError("Package is already bound elsewhere.", code="PACKAGE_MISMATCH")
            return attempt
        grant.status = AttemptGrantStatus.CONSUMED
        grant.save(update_fields=["status", "updated_at"])
        OfflineSyncService._materialize_attempt_from_package(
            attempt=attempt, package=package
        )
        return attempt

    @staticmethod
    def _materialize_attempt_from_package(*, attempt, package):
        question_ids = [item["public_id"] for item in package.content["questions"]]
        questions = {
            str(item.public_id): item
            for item in PublishedExamQuestion.objects.filter(
                revision=package.published_revision, public_id__in=question_ids
            )
        }
        if set(questions) != set(question_ids):
            raise OfflineSyncError("Package question mapping is invalid.", code="PACKAGE_INTEGRITY_ERROR")
        AttemptQuestion.objects.bulk_create([
            AttemptQuestion(
                attempt=attempt,
                published_question=questions[item["public_id"]],
                display_order=order,
            )
            for order, item in enumerate(package.content["questions"], 1)
        ])
        attempt_questions = {
            str(item.published_question.public_id): item
            for item in attempt.attempt_questions.select_related("published_question")
        }
        for question_payload in package.content["questions"]:
            attempt_question = attempt_questions[question_payload["public_id"]]
            if "choices" in question_payload:
                choice_ids = [item["public_id"] for item in question_payload["choices"]]
                choices = {
                    str(item.public_id): item
                    for item in PublishedExamChoice.objects.filter(
                        published_question=attempt_question.published_question,
                        public_id__in=choice_ids,
                    )
                }
                if set(choices) != set(choice_ids):
                    raise OfflineSyncError("Package choice mapping is invalid.", code="PACKAGE_INTEGRITY_ERROR")
                AttemptQuestionOption.objects.bulk_create([
                    AttemptQuestionOption(
                        attempt_question=attempt_question,
                        published_choice=choices[item["public_id"]],
                        display_order=order,
                    )
                    for order, item in enumerate(question_payload["choices"], 1)
                ])
            matching = question_payload.get("matching")
            if matching:
                all_items = matching["left"] + matching["right"]
                item_ids = [item["public_id"] for item in all_items]
                items = {
                    str(item.public_id): item
                    for item in PublishedExamMatchingItem.objects.filter(
                        published_question=attempt_question.published_question,
                        public_id__in=item_ids,
                    )
                }
                if set(items) != set(item_ids):
                    raise OfflineSyncError("Package matching mapping is invalid.", code="PACKAGE_INTEGRITY_ERROR")
                rows = []
                for side, values in (
                    (AttemptMatchingItem.Side.LEFT, matching["left"]),
                    (AttemptMatchingItem.Side.RIGHT, matching["right"]),
                ):
                    rows.extend(
                        AttemptMatchingItem(
                            attempt_question=attempt_question,
                            published_item=items[item["public_id"]],
                            side=side,
                            display_order=order,
                        )
                        for order, item in enumerate(values, 1)
                    )
                AttemptMatchingItem.objects.bulk_create(rows)

    @staticmethod
    def _load_verified_attempt(
        *, student, attempt_id, package_id, package_hash, package_signature,
        grant_token,
    ):
        try:
            attempt = ExamAttempt.objects.select_related(
                "offline_package__published_revision",
                "offline_package__attempt_grant",
                "attempt_grant",
            ).get(public_id=attempt_id, student=student)
        except ExamAttempt.DoesNotExist as exc:
            raise OfflineSyncError("Attempt was not found.", code="PACKAGE_MISMATCH") from exc
        package = attempt.offline_package
        if package is None or str(package.public_id) != str(package_id):
            raise OfflineSyncError("Attempt is not bound to this package.", code="PACKAGE_MISMATCH")
        OfflineSyncService._verify_package_credentials(
            package=package,
            student=student,
            package_hash=package_hash,
            package_signature=package_signature,
            grant_token=grant_token,
        )
        return attempt

    @staticmethod
    def sync(
        *, student, attempt_id, package_id, package_hash, package_signature,
        grant_token, client_id, known_server_revision, events,
        protocol_version=1, event_cutoff=None,
    ):
        OfflineSyncService._verify_protocol(protocol_version)
        if len(events) > OfflineSyncService.MAX_BATCH_EVENTS:
            raise OfflineSyncError("Sync batch is too large.", code="BATCH_TOO_LARGE")
        attempt = OfflineSyncService._load_verified_attempt(
            student=student,
            attempt_id=attempt_id,
            package_id=package_id,
            package_hash=package_hash,
            package_signature=package_signature,
            grant_token=grant_token,
        )
        attempt.refresh_from_db(fields=["revision"])
        if known_server_revision > attempt.revision:
            raise OfflineSyncError(
                "Client revision is ahead of the server.", code="CLIENT_REVISION_AHEAD"
            )
        questions = {
            str(item.published_question.public_id): item
            for item in attempt.attempt_questions.select_related("published_question")
        }
        outcomes = []
        # Each event is its own atomic mutation. Envelope/integrity failures reject
        # the whole request; a malformed event rolls back only its savepoint.
        for event in events:
            event_id = str(event["event_id"])
            if event_cutoff is not None and event["client_timestamp"] > event_cutoff:
                outcomes.append({"event_id": event_id, "outcome": "REJECTED", "code": "EVENT_AFTER_SUBMISSION"})
                continue
            question = questions.get(str(event["question_id"]))
            if question is None:
                outcomes.append({"event_id": event_id, "outcome": "REJECTED", "code": "UNKNOWN_QUESTION"})
                continue
            if event["client_id"] != client_id:
                outcomes.append({"event_id": event_id, "outcome": "REJECTED", "code": "CLIENT_MISMATCH"})
                continue
            try:
                result = OfflineSyncService._apply_event_locked(
                    attempt=attempt,
                    attempt_question=question,
                    operation=event["operation"],
                    payload=event.get("payload", {}),
                    event_id=event["event_id"],
                    client_id=client_id,
                    client_sequence=event["client_sequence"],
                    base_revision=event.get("base_revision"),
                    client_timestamp=event["client_timestamp"],
                    student=student,
                    origin=AnswerEventOrigin.OFFLINE_SYNC,
                )
                outcomes.append({
                    "event_id": event_id,
                    "outcome": result.outcome,
                    "server_revision": result.event.server_revision,
                })
            except OfflineSyncError:
                raise
            except (ValidationError, ValueError, TypeError) as exc:
                outcomes.append({
                    "event_id": event_id,
                    "outcome": "REJECTED",
                    "code": OfflineSyncService._event_error_code(attempt, event, exc),
                })
        attempt.refresh_from_db()
        return OfflineSyncResult(attempt=attempt, events=outcomes)

    @staticmethod
    @transaction.atomic
    def _apply_event_locked(*, attempt, attempt_question, **event_kwargs):
        # The full offline mutation lock order is exam -> grant -> package ->
        # attempt -> attempt question -> client state/event.
        CBTExam.objects.select_for_update().get(pk=attempt.cbt_exam_id)
        grant_model = attempt.attempt_grant.__class__
        grant = grant_model.objects.select_for_update().get(pk=attempt.attempt_grant_id)
        if grant.status == AttemptGrantStatus.REVOKED:
            raise OfflineSyncError("Grant has been revoked.", code="GRANT_REVOKED")
        OfflineExamPackage.objects.select_for_update().get(pk=attempt.offline_package_id)
        locked_attempt = ExamAttempt.objects.select_for_update().get(pk=attempt.pk)
        locked_question = AttemptQuestion.objects.select_for_update().get(
            pk=attempt_question.pk, attempt=locked_attempt
        )
        return StudentAnswerService.apply_answer_event(
            attempt_question=locked_question, **event_kwargs
        )

    @staticmethod
    def _event_error_code(attempt, event, exc):
        if attempt.status == ExamAttemptStatus.SUBMITTED:
            return "ATTEMPT_ALREADY_SUBMITTED"
        timestamp = event.get("client_timestamp")
        if timestamp and not (attempt.started_at <= timestamp < attempt.expires_at):
            return "EVENT_OUTSIDE_WINDOW"
        message = " ".join(getattr(exc, "messages", [str(exc)])).casefold()
        if "event identifier" in message:
            return "EVENT_ID_CONFLICT"
        if "client sequence" in message:
            return "CLIENT_SEQUENCE_STALE"
        return "INVALID_PAYLOAD"

    @staticmethod
    @transaction.atomic
    def sync_and_submit(*, submission_id, client_submitted_at=None, **sync_kwargs):
        # Acquire and retain the attempt lock before any event mutation and until
        # the submission snapshot is committed.
        attempt_id = sync_kwargs["attempt_id"]
        student = sync_kwargs["student"]
        try:
            ref = ExamAttempt.objects.get(public_id=attempt_id, student=student)
        except ExamAttempt.DoesNotExist as exc:
            raise OfflineSyncError("Attempt was not found.", code="PACKAGE_MISMATCH") from exc
        CBTExam.objects.select_for_update().get(pk=ref.cbt_exam_id)
        grant_model = ref.attempt_grant.__class__
        grant_model.objects.select_for_update().get(pk=ref.attempt_grant_id)
        OfflineExamPackage.objects.select_for_update().get(pk=ref.offline_package_id)
        ExamAttempt.objects.select_for_update().get(pk=ref.pk)
        sync_kwargs["event_cutoff"] = client_submitted_at
        result = OfflineSyncService.sync(**sync_kwargs)
        attempt = ExamAttempt.objects.select_for_update().get(pk=result.attempt.pk)
        if client_submitted_at is None or timezone.is_naive(client_submitted_at):
            raise OfflineSyncError("Submission timestamp must include a timezone.", code="INVALID_PAYLOAD")
        if not (attempt.started_at <= client_submitted_at < attempt.expires_at):
            raise OfflineSyncError("Submission occurred outside the attempt window.", code="ATTEMPT_EXPIRED")
        submission = ExamAttemptService.submit(
            attempt=attempt,
            submission_id=submission_id,
            allow_expired_reconciliation=True,
            client_submitted_at=client_submitted_at,
        )
        return result, submission
