import uuid
from datetime import timedelta
from unittest.mock import patch

from django.db.models import Max
from rest_framework import status

from cbt.models import (
    AnswerEventOrigin,
    AttemptAnswerEvent,
    AttemptGrantStatus,
    ExamAttempt,
    QuestionType,
)
from cbt.services import OfflinePackageService
from cbt.tests.test_phase5_offline_package import PhaseFiveOfflinePackageTests


class PhaseSixOfflineSyncTests(PhaseFiveOfflinePackageTests):
    """Phase 6 protocol tests also retain inherited Phase 5 guarantees."""

    def setUp(self):
        super().setUp()
        package = OfflinePackageService.issue(
            student=self.student,
            exam=self.exam,
            grant_token=self.grant_token,
            now=self.now,
        )
        self.package_payload = OfflinePackageService.response_payload(
            package=package,
            grant_token=self.grant_token,
            server_time=self.now,
        )
        self.package_id = self.package_payload["package_id"]
        self.package_hash = self.package_payload["package_hash"]
        self.package_signature = self.package_payload["package_signature"]
        self.client_id = uuid.uuid4()
        self.offline_started_at = self.grant.valid_from + timedelta(minutes=1)

    def credentials(self, **extra):
        return {
            "protocol_version": 1,
            "package_id": self.package_id,
            "package_hash": self.package_hash,
            "package_signature": self.package_signature,
            "grant_token": self.grant_token,
            "client_id": str(self.client_id),
            **extra,
        }

    def bootstrap(self, **extra):
        values = {"offline_started_at": self.offline_started_at.isoformat(), **extra}
        with patch(
            "cbt.services.offline_sync_service.timezone.now",
            return_value=self.offline_started_at + timedelta(minutes=1),
        ):
            return self.client.post(
                "/api/cbt/student/offline-attempts/start/",
                self.credentials(**values),
                format="json",
            )

    def sync(self, attempt_id, events=None, **extra):
        return self.client.post(
            f"/api/cbt/student/attempts/{attempt_id}/sync/",
            self.credentials(
                known_server_revision=extra.pop("known_server_revision", 0),
                events=events or [],
                **extra,
            ),
            format="json",
        )

    def event(self, question, *, sequence=1, payload=None, operation="SET", **extra):
        return {
            "event_id": str(extra.pop("event_id", uuid.uuid4())),
            "client_id": str(extra.pop("client_id", self.client_id)),
            "client_sequence": sequence,
            "base_revision": extra.pop("base_revision", 0),
            "question_id": question["public_id"],
            "operation": operation,
            "payload": payload or {},
            "client_timestamp": extra.pop(
                "client_timestamp", self.offline_started_at + timedelta(minutes=1)
            ).isoformat(),
            **extra,
        }

    def test_download_alone_does_not_start_and_bootstrap_is_idempotent(self):
        self.assertFalse(ExamAttempt.objects.exists())
        first = self.bootstrap()
        self.assertEqual(first.status_code, status.HTTP_200_OK, first.data)
        second = self.bootstrap()
        self.assertEqual(second.status_code, status.HTTP_200_OK, second.data)
        self.assertEqual(first.data["attempt"]["public_id"], second.data["attempt"]["public_id"])
        self.assertEqual(first.data["attempt"]["expires_at"], second.data["attempt"]["expires_at"])
        self.assertEqual(ExamAttempt.objects.count(), 1)

    def test_bootstrap_binds_exact_provenance_and_package_presentation(self):
        response = self.bootstrap()
        attempt = ExamAttempt.objects.get(public_id=response.data["attempt"]["public_id"])
        self.assertEqual(attempt.offline_package_id, self.grant.offline_package.pk)
        self.assertEqual(attempt.attempt_grant_id, self.grant.pk)
        self.assertEqual(attempt.published_revision_id, self.revision.pk)
        actual = list(attempt.attempt_questions.order_by("display_order"))
        self.assertEqual(
            [str(item.published_question.public_id) for item in actual],
            [item["public_id"] for item in self.package_payload["questions"]],
        )
        packaged_by_id = {item["public_id"]: item for item in self.package_payload["questions"]}
        for question in actual:
            packaged = packaged_by_id[str(question.published_question.public_id)]
            self.assertEqual(
                [str(item.published_choice.public_id) for item in question.option_order.all()],
                [item["public_id"] for item in packaged.get("choices", [])],
            )
            matching = packaged.get("matching")
            if matching:
                self.assertEqual(
                    [str(item.published_item.public_id) for item in question.matching_item_order.filter(side="RIGHT")],
                    [item["public_id"] for item in matching["right"]],
                )

    def test_start_window_protocol_and_integrity_rejections(self):
        before = self.bootstrap(
            offline_started_at=(self.grant.valid_from - timedelta(seconds=1)).isoformat()
        )
        self.assertEqual(before.data["code"], "START_OUTSIDE_GRANT_WINDOW")
        bad_hash = self.bootstrap(package_hash="0" * 64)
        self.assertEqual(bad_hash.data["code"], "PACKAGE_INTEGRITY_ERROR")
        bad_signature = self.bootstrap(package_signature="tampered")
        self.assertEqual(bad_signature.data["code"], "PACKAGE_INTEGRITY_ERROR")
        unsupported = self.bootstrap(protocol_version=999)
        self.assertEqual(unsupported.data["code"], "UNSUPPORTED_SYNC_VERSION")
        future = self.bootstrap(
            offline_started_at=(self.offline_started_at + timedelta(hours=1)).isoformat()
        )
        self.assertEqual(future.data["code"], "INVALID_START_TIME")
        self.assertFalse(ExamAttempt.objects.exists())

    def test_unsupported_package_schema_is_rejected_at_bootstrap(self):
        package = self.grant.offline_package
        package.__class__.objects.filter(pk=package.pk).update(schema_version=999)
        response = self.bootstrap()
        self.assertEqual(response.data["code"], "UNSUPPORTED_PACKAGE_VERSION")
        self.assertFalse(ExamAttempt.objects.exists())

    def test_revoked_grant_and_wrong_student_are_rejected(self):
        self.grant.status = AttemptGrantStatus.REVOKED
        self.grant.save(update_fields=["status"])
        revoked = self.bootstrap()
        self.assertEqual(revoked.data["code"], "GRANT_REVOKED")
        self.client.force_authenticate(user=self.other_student_user)
        wrong_student = self.bootstrap()
        self.assertEqual(wrong_student.data["code"], "PACKAGE_NOT_FOUND")

    def test_empty_sync_returns_authoritative_state_without_grading(self):
        started = self.bootstrap()
        response = self.sync(started.data["attempt"]["public_id"])
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["events"], [])
        self.assertEqual(len(response.data["answers"]), 8)
        serialized = str(response.data).casefold()
        for forbidden in ("is_correct", "expected_value", "marks_awarded", "grading"):
            self.assertNotIn(forbidden, serialized)

    def test_all_eight_payload_types_use_phase2_journal(self):
        attempt_id = self.bootstrap().data["attempt"]["public_id"]
        questions = {item["question_type"]: item for item in self.package_payload["questions"]}
        payloads = {
            QuestionType.SINGLE_CHOICE: {"option_ids": [questions[QuestionType.SINGLE_CHOICE]["choices"][0]["public_id"]]},
            QuestionType.MULTIPLE_CHOICE: {"option_ids": [questions[QuestionType.MULTIPLE_CHOICE]["choices"][0]["public_id"]]},
            QuestionType.TRUE_FALSE: {"option_ids": [questions[QuestionType.TRUE_FALSE]["choices"][0]["public_id"]]},
            QuestionType.SHORT_ANSWER: {"text": "offline short"},
            QuestionType.NUMERIC: {"value": "41.5"},
            QuestionType.FILL_BLANK: {"responses": {questions[QuestionType.FILL_BLANK]["blanks"][0]["public_id"]: "offline blank"}},
            QuestionType.MATCHING: {
                "matches": {
                    left["public_id"]: right["public_id"]
                    for left, right in zip(
                        questions[QuestionType.MATCHING]["matching"]["left"],
                        questions[QuestionType.MATCHING]["matching"]["right"],
                    )
                }
            },
            QuestionType.ESSAY: {"text": "offline essay response"},
        }
        events = [self.event(question, payload=payloads[q_type]) for q_type, question in questions.items()]
        response = self.sync(attempt_id, events)
        self.assertEqual([item["outcome"] for item in response.data["events"]], ["ACCEPTED"] * 8)
        self.assertEqual(response.data["attempt"]["revision"], 8)
        self.assertEqual(AttemptAnswerEvent.objects.filter(origin=AnswerEventOrigin.OFFLINE_SYNC).count(), 8)

    def test_replay_stale_and_question_scoped_sequences(self):
        attempt_id = self.bootstrap().data["attempt"]["public_id"]
        questions_by_type = {
            item["question_type"]: item
            for item in self.package_payload["questions"]
        }
        first_question = questions_by_type[QuestionType.SINGLE_CHOICE]
        second_question = questions_by_type[QuestionType.MULTIPLE_CHOICE]
        event = self.event(first_question, sequence=2, payload={"option_ids": []})
        accepted = self.sync(attempt_id, [event])
        duplicate = self.sync(attempt_id, [event], known_server_revision=1)
        stale = self.sync(attempt_id, [self.event(first_question, sequence=1, payload={"option_ids": []})], known_server_revision=1)
        other = self.sync(attempt_id, [self.event(second_question, sequence=1, payload={"option_ids": []})], known_server_revision=1)
        self.assertEqual(accepted.data["events"][0]["outcome"], "ACCEPTED")
        self.assertEqual(duplicate.data["events"][0]["outcome"], "DUPLICATE")
        self.assertEqual(stale.data["events"][0]["outcome"], "STALE")
        self.assertEqual(other.data["events"][0]["outcome"], "ACCEPTED")
        self.assertEqual(other.data["attempt"]["revision"], 2)

    def test_invalid_siblings_are_partial_and_unknown_question_is_rejected(self):
        attempt_id = self.bootstrap().data["attempt"]["public_id"]
        question = next(item for item in self.package_payload["questions"] if item["question_type"] == QuestionType.SINGLE_CHOICE)
        invalid = self.event(question, payload={"option_ids": [str(uuid.uuid4())]})
        unknown = self.event({"public_id": str(uuid.uuid4())}, payload={"text": "x"})
        valid = self.event(question, sequence=2, payload={"option_ids": []})
        response = self.sync(attempt_id, [invalid, unknown, valid])
        self.assertEqual([item["outcome"] for item in response.data["events"]], ["REJECTED", "REJECTED", "ACCEPTED"])
        self.assertEqual(response.data["attempt"]["revision"], 1)

    def test_window_batch_limit_and_revision_ahead(self):
        attempt_id = self.bootstrap().data["attempt"]["public_id"]
        question = self.package_payload["questions"][0]
        outside = self.sync(attempt_id, [self.event(question, client_timestamp=self.grant.valid_until)])
        self.assertEqual(outside.data["events"][0]["code"], "EVENT_OUTSIDE_WINDOW")
        ahead = self.sync(attempt_id, known_server_revision=99)
        self.assertEqual(ahead.data["code"], "CLIENT_REVISION_AHEAD")
        oversized = self.sync(attempt_id, [self.event(question, sequence=index + 1) for index in range(101)])
        self.assertEqual(oversized.data["code"], "BATCH_TOO_LARGE")

    def test_sync_before_submit_and_submission_retry(self):
        attempt_id = self.bootstrap().data["attempt"]["public_id"]
        question = next(item for item in self.package_payload["questions"] if item["question_type"] == QuestionType.ESSAY)
        event = self.event(question, payload={"text": "final offline answer"})
        body = self.credentials(
            known_server_revision=0,
            events=[event],
            submission_id=str(uuid.uuid4()),
            client_submitted_at=(self.offline_started_at + timedelta(minutes=2)).isoformat(),
        )
        url = f"/api/cbt/student/attempts/{attempt_id}/offline-submit/"
        first = self.client.post(url, body, format="json")
        retry = self.client.post(url, body, format="json")
        self.assertEqual(first.data["submission_outcome"], "ACCEPTED")
        self.assertEqual(retry.data["submission_outcome"], "DUPLICATE")
        attempt = ExamAttempt.objects.get(public_id=attempt_id)
        self.assertEqual(attempt.submitted_revision, 1)
        self.assertEqual(attempt.answer_events.aggregate(value=Max("server_revision"))["value"], 1)

    def test_event_after_submission_intent_is_excluded_from_snapshot(self):
        attempt_id = self.bootstrap().data["attempt"]["public_id"]
        submitted_at = self.offline_started_at + timedelta(minutes=2)
        event = self.event(
            self.package_payload["questions"][0],
            client_timestamp=submitted_at + timedelta(seconds=1),
        )
        response = self.client.post(
            f"/api/cbt/student/attempts/{attempt_id}/offline-submit/",
            self.credentials(
                known_server_revision=0,
                events=[event],
                submission_id=str(uuid.uuid4()),
                client_submitted_at=submitted_at.isoformat(),
            ),
            format="json",
        )
        self.assertEqual(response.data["events"][0]["code"], "EVENT_AFTER_SUBMISSION")
        self.assertEqual(response.data["attempt"]["submitted_revision"], 0)
