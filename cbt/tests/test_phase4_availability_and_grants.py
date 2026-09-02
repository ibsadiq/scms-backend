from datetime import timedelta

from django.core import signing
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework import status

from examination.models import AssessmentComponent

from cbt.models import (
    AttemptExpiryPolicy,
    AttemptGrant,
    AttemptGrantStatus,
    CBTExam,
    CBTExamStatus,
    ExamAttempt,
    ExamAttemptStatus,
    ExamQuestion,
    QuestionType,
)
from cbt.services import (
    AttemptGrantService,
    CBTExamAccessService,
    ExamAccessState,
    ExamAttemptService,
    PublishedExamRevisionService,
    QuestionBankService,
)
from cbt.tests.base import CBTAPITestBase


class PhaseFourAvailabilityAndGrantTests(CBTAPITestBase):
    def setUp(self):
        super().setUp()
        self.now = timezone.now().replace(microsecond=0)
        self.exam = CBTExam.objects.create(
            session=self.session,
            component=self.component,
            subject=self.subj_math,
            classroom=self.classroom_jss1,
            title="Phase 4 authorization",
            duration_minutes=60,
            available_from=self.now - timedelta(minutes=10),
            available_until=self.now + timedelta(minutes=30),
            attempt_expiry_policy=AttemptExpiryPolicy.CAP_AT_EXAM_CLOSE,
            status=CBTExamStatus.PUBLISHED,
            created_by=self.teacher_1,
        )
        question = QuestionBankService.create_question(
            subject=self.subj_math,
            grade_levels=[self.grade_jss1],
            question_type=QuestionType.SINGLE_CHOICE,
            text="Authorized question",
            created_by=self.teacher_1,
            options=[
                {"text": "Yes", "is_correct": True},
                {"text": "No", "is_correct": False},
            ],
        )
        ExamQuestion.objects.create(
            cbt_exam=self.exam,
            question_version=question.current_version,
            order=1,
            marks=10,
        )
        self.revision = PublishedExamRevisionService.ensure_current_for_exam(self.exam)

    def decision(self, at):
        return CBTExamAccessService.evaluate(
            student=self.student,
            exam=self.exam,
            now=at,
            revision=self.revision,
        )

    def test_availability_boundaries_are_open_inclusive_close_exclusive(self):
        self.exam.available_from = self.now
        self.exam.available_until = self.now + timedelta(hours=1)
        self.exam.save(update_fields=["available_from", "available_until"])
        self.assertEqual(
            self.decision(self.now - timedelta(microseconds=1)).state,
            ExamAccessState.NOT_YET_OPEN,
        )
        self.assertEqual(self.decision(self.now).state, ExamAccessState.AVAILABLE)
        self.assertEqual(
            self.decision(self.exam.available_until).state,
            ExamAccessState.CLOSED,
        )

    def test_student_metadata_returns_authoritative_structured_availability(self):
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get(f"/api/cbt/student/exams/{self.exam.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        availability = response.data["availability"]
        self.assertEqual(availability["status"], ExamAccessState.AVAILABLE)
        self.assertTrue(availability["can_start"])
        self.assertFalse(availability["can_resume"])
        self.assertIn("server_time", availability)
        self.assertEqual(
            response.data["published_revision"]["public_id"],
            str(self.revision.public_id),
        )

    def test_invalid_availability_range_is_rejected(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.patch(
            f"/api/cbt/exams/{self.exam.pk}/availability/",
            {
                "available_from": self.now.isoformat(),
                "available_until": self.now.isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_expiry_policy_caps_at_close_or_allows_duration(self):
        capped = ExamAttemptService.start_attempt(
            exam=self.exam, student=self.student, now=self.now
        )
        self.assertEqual(capped.expires_at, self.exam.available_until)

        # A separate exam is needed because ordinary CBT remains one attempt/exam.
        component = AssessmentComponent.objects.create(
            scheme=self.grading_scheme,
            name="Phase 4 duration only",
            max_score=100,
            weight=0,
            order=93,
        )
        duration_exam = CBTExam.objects.create(
            session=self.session,
            component=component,
            subject=self.subj_math,
            classroom=self.classroom_jss1,
            title="Duration only",
            duration_minutes=60,
            available_from=self.now - timedelta(minutes=1),
            available_until=self.now + timedelta(minutes=5),
            attempt_expiry_policy=AttemptExpiryPolicy.DURATION_ONLY,
            status=CBTExamStatus.PUBLISHED,
            created_by=self.teacher_1,
        )
        source = self.exam.exam_questions.get()
        ExamQuestion.objects.create(
            cbt_exam=duration_exam,
            question_version=source.question_version,
            order=1,
            marks=10,
        )
        PublishedExamRevisionService.ensure_current_for_exam(duration_exam)
        duration_attempt = ExamAttemptService.start_attempt(
            exam=duration_exam, student=self.student, now=self.now
        )
        self.assertEqual(duration_attempt.expires_at, self.now + timedelta(minutes=60))
        decision = CBTExamAccessService.evaluate(
            student=self.student,
            exam=duration_exam,
            now=duration_exam.available_until + timedelta(minutes=1),
            attempt=duration_attempt,
        )
        self.assertEqual(decision.state, ExamAccessState.ACTIVE_ATTEMPT)
        self.assertTrue(decision.can_resume)
        duration_exam.available_until = self.now - timedelta(seconds=1)
        duration_exam.save(update_fields=["available_until", "updated_at"])
        attempt_question = duration_attempt.attempt_questions.get()
        choice = attempt_question.published_question.choices.get(text="Yes")
        self.client.force_authenticate(user=self.student_user)
        saved = self.client.put(
            f"/api/cbt/attempt-questions/{attempt_question.pk}/answer/",
            {"option_ids": [str(choice.public_id)]},
            format="json",
        )
        self.assertEqual(saved.status_code, status.HTTP_200_OK, saved.data)
        submitted = self.client.post(
            f"/api/cbt/student/attempts/{duration_attempt.pk}/submit/",
            {},
            format="json",
        )
        self.assertEqual(submitted.status_code, status.HTTP_200_OK, submitted.data)

    def test_eligibility_and_missing_revision_fail_safely(self):
        wrong_student = CBTExamAccessService.evaluate(
            student=self.other_student,
            exam=self.exam,
            now=self.now,
            revision=self.revision,
        )
        self.assertEqual(wrong_student.state, ExamAccessState.NOT_ELIGIBLE)

        component = AssessmentComponent.objects.create(
            scheme=self.grading_scheme, name="No revision", max_score=100,
            weight=0, order=94,
        )
        no_revision = CBTExam.objects.create(
            session=self.session, component=component, subject=self.subj_math,
            classroom=self.classroom_jss1, title="No revision",
            duration_minutes=30, status=CBTExamStatus.PUBLISHED,
            created_by=self.teacher_1,
        )
        decision = CBTExamAccessService.evaluate(
            student=self.student, exam=no_revision, now=self.now
        )
        self.assertEqual(decision.state, ExamAccessState.NO_PUBLISHED_REVISION)

    def test_grant_issue_is_idempotent_and_bound_to_exact_revision(self):
        first = AttemptGrantService.issue(
            student=self.student, exam=self.exam, now=self.now
        )
        second = AttemptGrantService.issue(
            student=self.student, exam=self.exam, now=self.now
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.published_revision_id, self.revision.pk)
        self.assertEqual(first.valid_from, self.now)
        self.assertEqual(first.valid_until, self.exam.available_until)
        self.assertEqual(AttemptGrant.objects.count(), 1)

    def test_offline_preparation_grant_can_be_issued_before_opening(self):
        future_open = self.now + timedelta(hours=1)
        future_close = self.now + timedelta(hours=3)
        self.exam.available_from = future_open
        self.exam.available_until = future_close
        self.exam.save(update_fields=["available_from", "available_until"])
        self.client.force_authenticate(user=self.student_user)
        response = self.client.post(
            f"/api/cbt/student/exams/{self.exam.pk}/grant/", {}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        grant = AttemptGrant.objects.get(public_id=response.data["public_id"])
        self.assertEqual(grant.valid_from, future_open)
        self.assertEqual(grant.valid_until, future_close)
        with self.assertRaises(ValidationError):
            AttemptGrantService.verify_token(
                response.data["grant_token"], now=self.now,
                expected_student=self.student,
            )

    def test_signed_token_verification_and_tamper_rejection(self):
        grant = AttemptGrantService.issue(
            student=self.student, exam=self.exam, now=self.now
        )
        token = AttemptGrantService.sign(grant)
        original_token = token
        verified = AttemptGrantService.verify_token(
            token, now=self.now, expected_student=self.student
        )
        self.assertEqual(verified.grant.pk, grant.pk)
        with self.assertRaises(ValidationError):
            AttemptGrantService.verify_token(
                token, now=self.now, expected_student=self.other_student
            )
        with self.assertRaises(ValidationError):
            AttemptGrantService.verify_token(token + "tampered", now=self.now)

        for changed_claim in (
            {"student_binding": "wrong"},
            {"revision_id": "00000000-0000-0000-0000-000000000000"},
            {"revision_hash": "0" * 64},
            {"grant_id": "00000000-0000-0000-0000-000000000000"},
            {"valid_until": (self.now + timedelta(days=1)).isoformat()},
        ):
            claims = AttemptGrantService.claims_for(grant) | changed_claim
            resigned = signing.dumps(
                claims, salt=AttemptGrantService.TOKEN_SALT, compress=True
            )
            with self.assertRaises(ValidationError):
                AttemptGrantService.verify_token(resigned, now=self.now)

        unsupported = AttemptGrantService.claims_for(grant) | {"v": 999}
        unsupported_token = signing.dumps(
            unsupported, salt=AttemptGrantService.TOKEN_SALT, compress=True
        )
        with self.assertRaises(ValidationError):
            AttemptGrantService.verify_token(unsupported_token, now=self.now)

        type(self.revision).objects.filter(pk=self.revision.pk).update(
            content_hash="f" * 64
        )
        grant.published_revision.refresh_from_db()
        with self.assertRaises(ValidationError):
            AttemptGrantService.verify_token(
                original_token, now=self.now
            )

    def test_expired_and_revoked_grants_fail_verification_and_start(self):
        grant = AttemptGrantService.issue(
            student=self.student, exam=self.exam, now=self.now
        )
        token = AttemptGrantService.sign(grant)
        with self.assertRaises(ValidationError):
            AttemptGrantService.verify_token(token, now=grant.valid_until)

        AttemptGrantService.revoke(
            grant=grant, actor=self.teacher_user_1, reason="Security withdrawal"
        )
        with self.assertRaises(ValidationError):
            AttemptGrantService.verify_token(token, now=self.now)
        with self.assertRaises(ValidationError):
            ExamAttemptService.start_attempt(
                exam=self.exam, student=self.student, now=self.now
            )

    def test_start_consumes_grant_and_resume_is_idempotent(self):
        attempt = ExamAttemptService.start_attempt(
            exam=self.exam, student=self.student, now=self.now
        )
        attempt.attempt_grant.refresh_from_db()
        self.assertEqual(attempt.attempt_grant.status, AttemptGrantStatus.CONSUMED)
        self.assertEqual(attempt.attempt_grant.published_revision_id, attempt.published_revision_id)
        resumed = ExamAttemptService.start_attempt(
            exam=self.exam, student=self.student, now=self.now + timedelta(minutes=1)
        )
        self.assertEqual(resumed.pk, attempt.pk)
        self.assertEqual(ExamAttempt.objects.count(), 1)
        self.assertEqual(AttemptGrant.objects.count(), 1)

    def test_revoked_consumed_grant_cannot_resume(self):
        attempt = ExamAttemptService.start_attempt(
            exam=self.exam, student=self.student, now=self.now
        )
        AttemptGrantService.revoke(
            grant=attempt.attempt_grant,
            actor=self.teacher_user_1,
            reason="Invigilator revoked authorization",
        )
        decision = CBTExamAccessService.evaluate(
            student=self.student,
            exam=self.exam,
            now=self.now + timedelta(minutes=1),
            attempt=attempt,
        )
        self.assertEqual(decision.state, ExamAccessState.GRANT_REVOKED)
        self.assertFalse(decision.can_resume)
        with self.assertRaises(ValidationError):
            ExamAttemptService.start_attempt(
                exam=self.exam,
                student=self.student,
                now=self.now + timedelta(minutes=1),
            )

    def test_legacy_attempt_without_grant_remains_submittable(self):
        attempt = ExamAttempt.objects.create(
            cbt_exam=self.exam,
            student=self.student,
            enrollment=self.enrollment,
            published_revision=self.revision,
            status=ExamAttemptStatus.IN_PROGRESS,
            started_at=self.now,
            expires_at=self.now + timedelta(minutes=10),
        )
        result = ExamAttemptService.submit(attempt=attempt)
        self.assertEqual(result.attempt.status, ExamAttemptStatus.SUBMITTED)
        self.assertIsNone(result.attempt.attempt_grant_id)

    def test_student_grant_endpoint_never_accepts_another_student_identity(self):
        self.client.force_authenticate(user=self.student_user)
        response = self.client.post(
            f"/api/cbt/student/exams/{self.exam.pk}/grant/",
            {"student": self.other_student.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        grant = AttemptGrant.objects.get(public_id=response.data["public_id"])
        self.assertEqual(grant.student_id, self.student.pk)
        self.assertNotIn("student", response.data)
        self.assertNotIn("grading", str(response.data).lower())
