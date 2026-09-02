import uuid
from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from examination.models import AssessmentComponent

from cbt.models import (
    AttemptAnswerEvent,
    AttemptGrade,
    CBTExam,
    CBTExamStatus,
    ExamAttempt,
    ExamQuestion,
    QuestionType,
)
from cbt.services import QuestionBankService
from cbt.tests.base import CBTAPITestBase


class PhaseTwoSyncTests(CBTAPITestBase):
    def setUp(self):
        super().setUp()
        self.exam = CBTExam.objects.create(
            session=self.session,
            component=self.component,
            subject=self.subj_math,
            classroom=self.classroom_jss1,
            title="Phase 2 sync exam",
            duration_minutes=30,
            status=CBTExamStatus.PUBLISHED,
            created_by=self.teacher_1,
        )
        self.q1 = QuestionBankService.create_question(
            subject=self.subj_math,
            grade_levels=[self.grade_jss1],
            question_type=QuestionType.SINGLE_CHOICE,
            text="Q1",
            created_by=self.teacher_1,
            options=[
                {"text": "A", "is_correct": True},
                {"text": "B", "is_correct": False},
                {"text": "C", "is_correct": False},
            ],
        )
        self.q2 = QuestionBankService.create_question(
            subject=self.subj_math,
            grade_levels=[self.grade_jss1],
            question_type=QuestionType.SHORT_ANSWER,
            text="Q2",
            created_by=self.teacher_1,
            answer_definition={"accepted_answers": ["answer"]},
        )
        ExamQuestion.objects.create(
            cbt_exam=self.exam,
            question_version=self.q1.current_version,
            order=1,
            marks=5,
        )
        ExamQuestion.objects.create(
            cbt_exam=self.exam,
            question_version=self.q2.current_version,
            order=2,
            marks=5,
        )
        self.client.force_authenticate(user=self.student_user)
        self.started = self.client.post(
            f"/api/cbt/student/exams/{self.exam.pk}/start/"
        )
        self.attempt_id = self.started.data["id"]
        self.questions = self.started.data["questions"]
        self.choice_question = next(
            item for item in self.questions
            if item["question_type"] == QuestionType.SINGLE_CHOICE
        )
        self.text_question = next(
            item for item in self.questions
            if item["question_type"] == QuestionType.SHORT_ANSWER
        )
        self.options = {
            item["text"]: item["option_id"]
            for item in self.choice_question["options"]
        }
        self.client_id = uuid.uuid4()

    def event(self, sequence, **extra):
        return {
            "event_id": str(uuid.uuid4()),
            "client_id": str(self.client_id),
            "client_sequence": sequence,
            "base_revision": extra.pop("base_revision", 0),
            **extra,
        }

    def save_choice(self, sequence, option, **extra):
        payload = self.event(sequence, option_ids=[self.options[option]], **extra)
        return self.client.put(
            f"/api/cbt/attempt-questions/{self.choice_question['id']}/answer/",
            payload,
            format="json",
        )

    def test_public_identities_and_attempt_revision_are_stable(self):
        attempt = ExamAttempt.objects.get(pk=self.attempt_id)
        original_attempt_id = attempt.public_id
        original_question_ids = list(
            attempt.attempt_questions.order_by("display_order")
            .values_list("public_id", flat=True)
        )
        retrieved = self.client.get(f"/api/cbt/student/attempts/{attempt.pk}/")
        self.assertEqual(uuid.UUID(retrieved.data["public_id"]), original_attempt_id)
        self.assertEqual(
            [uuid.UUID(item["public_id"]) for item in retrieved.data["questions"]],
            original_question_ids,
        )
        self.assertEqual(retrieved.data["revision"], 0)
        self.assertIn("server_time", retrieved.data)

    def test_retry_is_idempotent_and_payload_reuse_is_rejected(self):
        event_id = uuid.uuid4()
        request = {
            "event_id": str(event_id),
            "client_id": str(self.client_id),
            "client_sequence": 1,
            "base_revision": 0,
            "option_ids": [self.options["A"]],
        }
        first = self.client.put(
            f"/api/cbt/attempt-questions/{self.choice_question['id']}/answer/",
            request,
            format="json",
        )
        retry = self.client.put(
            f"/api/cbt/attempt-questions/{self.choice_question['id']}/answer/",
            request,
            format="json",
        )
        self.assertEqual(first.data["sync"]["outcome"], "ACCEPTED")
        self.assertEqual(retry.data["sync"]["outcome"], "DUPLICATE")
        self.assertEqual(first.data["sync"]["attempt_revision"], 1)
        self.assertEqual(retry.data["sync"]["attempt_revision"], 1)
        self.assertEqual(AttemptAnswerEvent.objects.count(), 1)

        changed = dict(request, option_ids=[self.options["B"]])
        conflict = self.client.put(
            f"/api/cbt/attempt-questions/{self.choice_question['id']}/answer/",
            changed,
            format="json",
        )
        self.assertEqual(conflict.status_code, status.HTTP_400_BAD_REQUEST)

        wrong_question = dict(request, text="different")
        wrong_question.pop("option_ids")
        conflict = self.client.put(
            f"/api/cbt/attempt-questions/{self.text_question['id']}/answer/",
            wrong_question,
            format="json",
        )
        self.assertEqual(conflict.status_code, status.HTTP_400_BAD_REQUEST)

    def test_out_of_order_same_question_keeps_newest_sequence(self):
        self.assertEqual(self.save_choice(15, "A").status_code, status.HTTP_200_OK)
        newest = self.save_choice(27, "B", base_revision=1)
        delayed = self.save_choice(21, "C", base_revision=1)
        self.assertEqual(newest.data["sync"]["outcome"], "ACCEPTED")
        self.assertEqual(delayed.data["sync"]["outcome"], "STALE")
        self.assertEqual(delayed.data["sync"]["attempt_revision"], 2)
        self.assertEqual(
            delayed.data["question"]["student_response"]["option_ids"],
            [self.options["B"]],
        )
        self.assertEqual(ExamAttempt.objects.get(pk=self.attempt_id).revision, 2)

    def test_questions_have_independent_client_sequences(self):
        q1 = self.save_choice(27, "B")
        q2 = self.client.put(
            f"/api/cbt/attempt-questions/{self.text_question['id']}/answer/",
            self.event(1, text="answer", base_revision=0),
            format="json",
        )
        self.assertEqual(q1.data["sync"]["outcome"], "ACCEPTED")
        self.assertEqual(q2.data["sync"]["outcome"], "ACCEPTED")
        self.assertEqual(q2.data["sync"]["attempt_revision"], 2)

    def test_newer_clear_cannot_be_undone_by_delayed_set(self):
        self.save_choice(15, "A")
        clear_metadata = self.event(27, base_revision=1)
        cleared = self.client.delete(
            f"/api/cbt/attempt-questions/{self.choice_question['id']}/answer/",
            clear_metadata,
            format="json",
        )
        delayed = self.save_choice(21, "B", base_revision=1)
        self.assertEqual(cleared.data["sync"]["outcome"], "ACCEPTED")
        self.assertEqual(delayed.data["sync"]["outcome"], "STALE")
        self.assertIsNone(delayed.data["question"]["student_response"])

    def test_submission_is_idempotent_and_snapshot_is_stable(self):
        self.save_choice(1, "A")
        submission_id = uuid.uuid4()
        first = self.client.post(
            f"/api/cbt/student/attempts/{self.attempt_id}/submit/",
            {"submission_id": str(submission_id)},
            format="json",
        )
        retry = self.client.post(
            f"/api/cbt/student/attempts/{self.attempt_id}/submit/",
            {"submission_id": str(submission_id)},
            format="json",
        )
        different = self.client.post(
            f"/api/cbt/student/attempts/{self.attempt_id}/submit/",
            {"submission_id": str(uuid.uuid4())},
            format="json",
        )
        self.assertEqual(first.data["submission_outcome"], "ACCEPTED")
        self.assertEqual(retry.data["submission_outcome"], "DUPLICATE")
        self.assertEqual(different.data["submission_outcome"], "ALREADY_SUBMITTED")
        self.assertEqual(AttemptGrade.objects.filter(attempt_id=self.attempt_id).count(), 1)
        attempt = ExamAttempt.objects.get(pk=self.attempt_id)
        self.assertEqual(attempt.submission_id, submission_id)
        self.assertEqual(attempt.submitted_revision, attempt.revision)
        self.assertEqual(len(attempt.submission_snapshot_hash), 64)
        self.assertEqual(
            retry.data["attempt"]["submission_snapshot_hash"],
            first.data["attempt"]["submission_snapshot_hash"],
        )

        after_submit = self.save_choice(2, "B", base_revision=attempt.revision)
        self.assertEqual(after_submit.status_code, status.HTTP_400_BAD_REQUEST)

    def test_expired_attempt_rejects_event_despite_client_metadata(self):
        ExamAttempt.objects.filter(pk=self.attempt_id).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        response = self.save_choice(999, "A", base_revision=0)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(AttemptAnswerEvent.objects.count(), 0)

    def test_event_protocol_saves_every_supported_question_type(self):
        component = AssessmentComponent.objects.create(
            scheme=self.grading_scheme,
            name="Phase 2 all types",
            max_score=100,
            weight=0,
            order=2,
        )
        exam = CBTExam.objects.create(
            session=self.session,
            component=component,
            subject=self.subj_math,
            classroom=self.classroom_jss1,
            title="Phase 2 all types",
            duration_minutes=30,
            status=CBTExamStatus.PUBLISHED,
            created_by=self.teacher_1,
        )
        definitions = [
            (QuestionType.SINGLE_CHOICE, [{"text": "yes", "is_correct": True}, {"text": "no", "is_correct": False}], None),
            (QuestionType.MULTIPLE_CHOICE, [{"text": "a", "is_correct": True}, {"text": "b", "is_correct": True}], None),
            (QuestionType.TRUE_FALSE, [{"text": "true", "is_correct": True}, {"text": "false", "is_correct": False}], None),
            (QuestionType.SHORT_ANSWER, None, {"accepted_answers": ["short"]}),
            (QuestionType.NUMERIC, None, {"expected_value": "10", "tolerance": "0"}),
            (QuestionType.FILL_BLANK, None, {"blanks": [{"accepted_answers": ["blank"]}]}),
            (QuestionType.ESSAY, None, {"model_answer": "model", "marking_guide": "guide"}),
            (QuestionType.MATCHING, None, {"pairs": [{"left_text": "L1", "right_text": "R1"}, {"left_text": "L2", "right_text": "R2"}]}),
        ]
        for order, (question_type, options, answer_definition) in enumerate(definitions, 1):
            question = QuestionBankService.create_question(
                subject=self.subj_math,
                grade_levels=[self.grade_jss1],
                question_type=question_type,
                text=f"Phase 2 {question_type}",
                created_by=self.teacher_1,
                options=options,
                answer_definition=answer_definition,
            )
            ExamQuestion.objects.create(
                cbt_exam=exam,
                question_version=question.current_version,
                order=order,
                marks=1,
            )

        started = self.client.post(f"/api/cbt/student/exams/{exam.pk}/start/")
        for sequence, question in enumerate(started.data["questions"], 1):
            question_type = question["question_type"]
            payload = self.event(sequence)
            if question_type in {
                QuestionType.SINGLE_CHOICE,
                QuestionType.MULTIPLE_CHOICE,
                QuestionType.TRUE_FALSE,
            }:
                payload["option_ids"] = [question["options"][0]["option_id"]]
            elif question_type in {QuestionType.SHORT_ANSWER, QuestionType.ESSAY}:
                payload["text"] = "student response"
            elif question_type == QuestionType.NUMERIC:
                payload["value"] = "10"
            elif question_type == QuestionType.FILL_BLANK:
                payload["responses"] = {
                    str(question["blank_items"][0]["id"]): "blank"
                }
            elif question_type == QuestionType.MATCHING:
                left = question["matching_items"]["left_items"]
                right = question["matching_items"]["right_items"]
                payload["matches"] = {
                    left_item["id"]: right_item["id"]
                    for left_item, right_item in zip(left, right)
                }
            response = self.client.put(
                f"/api/cbt/attempt-questions/{question['id']}/answer/",
                payload,
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
            self.assertEqual(response.data["sync"]["outcome"], "ACCEPTED")
