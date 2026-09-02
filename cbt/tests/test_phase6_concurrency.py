import uuid
from datetime import timedelta

from django.db import connection
from django.utils import timezone

from academic.models import Student
from cbt.models import CBTExam, ExamAttempt, OfflineExamPackage
from cbt.services import (
    AttemptGrantService,
    OfflinePackageService,
    OfflineSyncService,
    PublishedExamRevisionService,
)
from cbt.tests.test_phase2_concurrency import PhaseTwoConcurrencyTests


class PhaseSixConcurrencyTests(PhaseTwoConcurrencyTests):
    """Real PostgreSQL races for the package bootstrap and event journal."""

    def setUp(self):
        super().setUp()
        now = timezone.now().replace(microsecond=0)
        CBTExam.objects.filter(pk=self.exam.pk).update(
            available_from=now - timedelta(minutes=1),
            available_until=now + timedelta(hours=2),
        )
        self.exam.refresh_from_db()
        PublishedExamRevisionService.ensure_current_for_exam(self.exam)
        self.grant = AttemptGrantService.issue(
            student=self.student,
            exam=self.exam,
            source="OFFLINE_PREPARATION",
            now=now,
        )
        self.grant_token = AttemptGrantService.sign(self.grant)
        self.package = OfflinePackageService.issue(
            student=self.student,
            exam=self.exam,
            grant_token=self.grant_token,
            now=now,
        )
        self.started_at = now
        self.client_id = uuid.uuid4()

    def bootstrap(self):
        connection.set_tenant(self.tenant)
        return OfflineSyncService.bootstrap(
            student=Student.objects.get(pk=self.student.pk),
            package_id=self.package.public_id,
            package_hash=self.package.package_hash,
            package_signature=self.package.package_signature,
            grant_token=self.grant_token,
            client_id=self.client_id,
            offline_started_at=self.started_at,
        )

    def test_concurrent_first_offline_bootstrap_creates_one_bound_attempt(self):
        results, errors = self.run_threads([
            lambda: self.bootstrap().pk,
            lambda: self.bootstrap().pk,
        ])
        self.assertEqual(errors, [])
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(ExamAttempt.objects.count(), 1)
        self.assertEqual(OfflineExamPackage.objects.get(pk=self.package.pk).attempt.pk, results[0])

    def test_concurrent_duplicate_offline_event_is_accepted_once(self):
        attempt = self.bootstrap()
        question = self.package.content["questions"][0]
        event_id = uuid.uuid4()
        event = {
            "event_id": event_id,
            "client_id": self.client_id,
            "client_sequence": 1,
            "base_revision": 0,
            "question_id": question["public_id"],
            "operation": "SET",
            "payload": {"option_ids": []},
            "client_timestamp": self.started_at + timedelta(seconds=1),
        }

        def sync():
            connection.set_tenant(self.tenant)
            result = OfflineSyncService.sync(
                student=Student.objects.get(pk=self.student.pk),
                attempt_id=attempt.public_id,
                package_id=self.package.public_id,
                package_hash=self.package.package_hash,
                package_signature=self.package.package_signature,
                grant_token=self.grant_token,
                client_id=self.client_id,
                known_server_revision=0,
                events=[event],
            )
            return result.events[0]["outcome"]

        results, errors = self.run_threads([sync, sync])
        self.assertEqual(errors, [])
        self.assertCountEqual(results, ["ACCEPTED", "DUPLICATE"])
        attempt.refresh_from_db()
        self.assertEqual(attempt.revision, 1)
        self.assertEqual(attempt.answer_events.filter(event_id=event_id).count(), 1)
