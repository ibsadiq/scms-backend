from unittest.mock import patch

from django.core.exceptions import ValidationError
from rest_framework import status

from examination.models import AssessmentEntry
from cbt.models import (
    AttemptGrade,
    AttemptGradingStatus,
    CBTExam,
    CBTExamStatus,
    ExamQuestion,
    QuestionAttachment,
    QuestionStatus,
    QuestionType,
)
from cbt.services import QuestionBankService
from cbt.tests.base import CBTAPITestBase


class PhaseOneQuestionDeliveryTests(CBTAPITestBase):
    def create_exam_with_question(self, question_type, answer_definition=None, options=None):
        exam = CBTExam.objects.create(
            session=self.session,
            component=self.component,
            subject=self.subj_math,
            classroom=self.classroom_jss1,
            title=f"{question_type} hardening exam",
            duration_minutes=30,
            status=CBTExamStatus.PUBLISHED,
            created_by=self.teacher_1,
        )
        question = QuestionBankService.create_question(
            subject=self.subj_math,
            grade_levels=[self.grade_jss1],
            question_type=question_type,
            text="Harden this question",
            created_by=self.teacher_1,
            options=options,
            answer_definition=answer_definition,
        )
        question.status = QuestionStatus.APPROVED
        question.save(update_fields=["status"])
        ExamQuestion.objects.create(
            cbt_exam=exam,
            question_version=question.current_version,
            order=1,
            marks=10,
        )
        return exam, question

    def start(self, exam):
        self.client.force_authenticate(user=self.student_user)
        response = self.client.post(f"/api/cbt/student/exams/{exam.pk}/start/")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response

    def test_matching_uses_opaque_unrelated_stable_ids_and_grades_correctly(self):
        exam, _ = self.create_exam_with_question(
            QuestionType.MATCHING,
            answer_definition={
                "pairs": [
                    {"left_text": "One", "right_text": "1"},
                    {"left_text": "Two", "right_text": "2"},
                    {"left_text": "Three", "right_text": "3"},
                ]
            },
        )
        started = self.start(exam)
        question = started.data["questions"][0]
        matching = question["matching_items"]

        left_ids = {item["id"] for item in matching["left_items"]}
        right_ids = {item["id"] for item in matching["right_items"]}
        self.assertTrue(left_ids.isdisjoint(right_ids))
        self.assertNotIn("matching_pair", str(started.data))
        self.assertNotIn("is_correct", str(started.data))

        retrieved = self.client.get(
            f"/api/cbt/student/attempts/{started.data['id']}/"
        )
        self.assertEqual(
            matching,
            retrieved.data["questions"][0]["matching_items"],
        )

        left_by_text = {item["text"]: item["id"] for item in matching["left_items"]}
        right_by_text = {item["text"]: item["id"] for item in matching["right_items"]}
        answer = self.client.put(
            f"/api/cbt/attempt-questions/{question['id']}/answer/",
            data={
                "matches": {
                    left_by_text["One"]: right_by_text["1"],
                    left_by_text["Two"]: right_by_text["2"],
                    left_by_text["Three"]: right_by_text["3"],
                }
            },
            format="json",
        )
        self.assertEqual(answer.status_code, status.HTTP_200_OK, answer.data)
        submitted = self.client.post(
            f"/api/cbt/student/attempts/{started.data['id']}/submit/"
        )
        self.assertEqual(submitted.status_code, status.HTTP_200_OK, submitted.data)
        grade = AttemptGrade.objects.get(attempt_id=started.data["id"])
        self.assertEqual(grade.raw_score, 10)

    def test_invalid_matching_answer_grades_incorrectly(self):
        exam, _ = self.create_exam_with_question(
            QuestionType.MATCHING,
            answer_definition={
                "pairs": [
                    {"left_text": "One", "right_text": "1"},
                    {"left_text": "Two", "right_text": "2"},
                ]
            },
        )
        started = self.start(exam)
        question = started.data["questions"][0]
        left = question["matching_items"]["left_items"]
        right = question["matching_items"]["right_items"]
        left_by_text = {item["text"]: item["id"] for item in left}
        right_by_text = {item["text"]: item["id"] for item in right}
        answer = self.client.put(
            f"/api/cbt/attempt-questions/{question['id']}/answer/",
            data={"matches": {left_by_text["One"]: right_by_text["2"], left_by_text["Two"]: right_by_text["1"]}},
            format="json",
        )
        self.assertEqual(answer.status_code, status.HTTP_200_OK, answer.data)
        self.client.post(f"/api/cbt/student/attempts/{started.data['id']}/submit/")
        grade = AttemptGrade.objects.get(attempt_id=started.data["id"])
        self.assertLess(grade.raw_score, 10)

    def test_fill_blank_end_to_end(self):
        exam, _ = self.create_exam_with_question(
            QuestionType.FILL_BLANK,
            answer_definition={
                "blanks": [
                    {"position": 1, "accepted_answers": ["four"]},
                    {"position": 2, "accepted_answers": ["five"]},
                ]
            },
        )
        started = self.start(exam)
        question = started.data["questions"][0]
        self.assertEqual([item["position"] for item in question["blank_items"]], [1, 2])
        responses = {str(item["id"]): value for item, value in zip(question["blank_items"], ["four", "five"])}
        saved = self.client.put(
            f"/api/cbt/attempt-questions/{question['id']}/answer/",
            data={"responses": responses},
            format="json",
        )
        self.assertEqual(saved.status_code, status.HTTP_200_OK, saved.data)
        self.client.post(f"/api/cbt/student/attempts/{started.data['id']}/submit/")
        self.assertEqual(AttemptGrade.objects.get(attempt_id=started.data["id"]).raw_score, 10)

    def test_generated_exam_dispatch_uses_version_question_type(self):
        exam, question = self.create_exam_with_question(
            QuestionType.SINGLE_CHOICE,
            options=[
                {"text": "Correct", "is_correct": True},
                {"text": "Wrong", "is_correct": False},
            ],
        )
        question.question_type = QuestionType.ESSAY
        question.save(update_fields=["question_type"])

        started = self.start(exam)
        payload = started.data["questions"][0]
        self.assertEqual(payload["question_type"], QuestionType.SINGLE_CHOICE)
        option_id = next(item["option_id"] for item in payload["options"] if item["text"] == "Correct")
        saved = self.client.put(
            f"/api/cbt/attempt-questions/{payload['id']}/answer/",
            data={"option_ids": [option_id]},
            format="json",
        )
        self.assertEqual(saved.status_code, status.HTTP_200_OK, saved.data)
        self.client.post(f"/api/cbt/student/attempts/{started.data['id']}/submit/")
        self.assertEqual(AttemptGrade.objects.get(attempt_id=started.data["id"]).raw_score, 10)

    def test_referenced_version_content_and_attachment_are_immutable(self):
        question = QuestionBankService.create_question(
            subject=self.subj_math,
            grade_levels=[self.grade_jss1],
            question_type=QuestionType.SINGLE_CHOICE,
            text="Frozen",
            created_by=self.teacher_1,
            options=[{"text": "Yes", "is_correct": True}, {"text": "No", "is_correct": False}],
        )
        attachment = QuestionAttachment.objects.create(
            question_version=question.current_version,
            file="cbt/question_attachments/diagram.txt",
        )
        exam = CBTExam.objects.create(
            session=self.session, component=self.component, subject=self.subj_math,
            classroom=self.classroom_jss1, title="Frozen", duration_minutes=30,
            status=CBTExamStatus.READY, created_by=self.teacher_1,
        )
        ExamQuestion.objects.create(
            cbt_exam=exam, question_version=question.current_version, order=1, marks=5
        )
        numeric_question = QuestionBankService.create_question(
            subject=self.subj_math,
            grade_levels=[self.grade_jss1],
            question_type=QuestionType.NUMERIC,
            text="Also frozen",
            created_by=self.teacher_1,
            answer_definition={"expected_value": "12", "tolerance": "0.5"},
        )
        ExamQuestion.objects.create(
            cbt_exam=exam,
            question_version=numeric_question.current_version,
            order=2,
            marks=5,
        )

        version = question.current_version
        version.text = "Changed"
        with self.assertRaises(ValidationError):
            version.save()
        option = version.options.first()
        option.is_correct = not option.is_correct
        with self.assertRaises(ValidationError):
            option.save()
        definition = numeric_question.current_version.numeric_answer_definition
        definition.tolerance = 10
        with self.assertRaises(ValidationError):
            definition.save()
        attachment.caption = "Changed"
        with self.assertRaises(ValidationError):
            attachment.save()
        with self.assertRaises(ValidationError):
            attachment.delete()

        self.client.force_authenticate(user=self.admin_user)
        self.assertEqual(
            self.client.patch(
                f"/api/cbt/question-attachments/{attachment.pk}/",
                {"caption": "API change"},
                format="json",
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/cbt/question-attachments/{attachment.pk}/"
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        new_version = QuestionBankService.create_new_version(
            question=question,
            text="Safe new version",
            created_by=self.teacher_1,
            options=[{"text": "Yes", "is_correct": True}, {"text": "No", "is_correct": False}],
        )
        self.assertNotEqual(new_version.pk, version.pk)

    def test_student_payloads_exclude_private_answer_definitions_for_all_types(self):
        exam = CBTExam.objects.create(
            session=self.session, component=self.component, subject=self.subj_math,
            classroom=self.classroom_jss1, title="All types", duration_minutes=30,
            status=CBTExamStatus.PUBLISHED, created_by=self.teacher_1,
        )
        definitions = [
            (QuestionType.SINGLE_CHOICE, [{"text": "yes", "is_correct": True}, {"text": "no", "is_correct": False}], None),
            (QuestionType.MULTIPLE_CHOICE, [{"text": "a", "is_correct": True}, {"text": "b", "is_correct": True}], None),
            (QuestionType.TRUE_FALSE, [{"text": "true", "is_correct": True}, {"text": "false", "is_correct": False}], None),
            (QuestionType.SHORT_ANSWER, None, {"accepted_answers": ["private-short"]}),
            (QuestionType.NUMERIC, None, {"expected_value": "123.456", "tolerance": "0.25"}),
            (QuestionType.FILL_BLANK, None, {"blanks": [{"accepted_answers": ["private-blank"]}]}),
            (QuestionType.ESSAY, None, {"model_answer": "private-model", "marking_guide": "private-rubric"}),
            (QuestionType.MATCHING, None, {"pairs": [{"left_text": "L1", "right_text": "R1"}, {"left_text": "L2", "right_text": "R2"}]}),
        ]
        for order, (question_type, options, answer_definition) in enumerate(definitions, start=1):
            question = QuestionBankService.create_question(
                subject=self.subj_math,
                grade_levels=[self.grade_jss1],
                question_type=question_type,
                text=f"Render {question_type}",
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

        started = self.start(exam)
        serialized = str(started.data)
        for secret in (
            "is_correct", "private-short", "123.456", "0.25",
            "private-blank", "private-model", "private-rubric",
        ):
            self.assertNotIn(secret, serialized)

    @patch("cbt.views.student.AttemptGradingService.grade_attempt", side_effect=RuntimeError("secret failure"))
    def test_grading_failure_is_observable_without_internal_leak(self, _grade):
        exam, _ = self.create_exam_with_question(
            QuestionType.SINGLE_CHOICE,
            options=[{"text": "Yes", "is_correct": True}, {"text": "No", "is_correct": False}],
        )
        started = self.start(exam)
        response = self.client.post(f"/api/cbt/student/attempts/{started.data['id']}/submit/")
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(response.data["grading_status"], AttemptGradingStatus.FAILED)
        self.assertNotIn("secret failure", str(response.data))
        grade = AttemptGrade.objects.get(attempt_id=started.data["id"])
        self.assertEqual(grade.status, AttemptGradingStatus.FAILED)
        self.assertIn("secret failure", grade.grading_error)


class PhaseOneLifecycleAndScopeTests(CBTAPITestBase):
    def exam_payload(self, exam):
        return {
            "title": f"{exam.title} changed",
            "session": self.session.id,
            "component": self.component.id,
            "subject": self.subj_math.id,
            "classroom": self.classroom_jss1.id,
            "duration_minutes": 45,
        }

    def test_draft_update_allowed_but_published_and_closed_crud_rejected(self):
        self.client.force_authenticate(user=self.teacher_user_1)
        draft = CBTExam.objects.create(
            session=self.session, component=self.component, subject=self.subj_math,
            classroom=self.classroom_jss1, title="Draft", duration_minutes=30,
            status=CBTExamStatus.DRAFT, created_by=self.teacher_1,
        )
        self.assertEqual(
            self.client.patch(f"/api/cbt/exams/{draft.pk}/", {"title": "Allowed"}, format="json").status_code,
            status.HTTP_200_OK,
        )

        exam = draft
        for lifecycle_status in (CBTExamStatus.PUBLISHED, CBTExamStatus.CLOSED):
            CBTExam.objects.filter(pk=exam.pk).update(status=lifecycle_status)
            exam.refresh_from_db()
            self.assertEqual(
                self.client.put(f"/api/cbt/exams/{exam.pk}/", self.exam_payload(exam), format="json").status_code,
                status.HTTP_400_BAD_REQUEST,
            )
            self.assertEqual(
                self.client.patch(f"/api/cbt/exams/{exam.pk}/", {"title": "Blocked"}, format="json").status_code,
                status.HTTP_400_BAD_REQUEST,
            )
            self.assertEqual(
                self.client.delete(f"/api/cbt/exams/{exam.pk}/").status_code,
                status.HTTP_400_BAD_REQUEST,
            )

    def test_question_answer_keys_are_subject_scoped(self):
        question = QuestionBankService.create_question(
            subject=self.subj_math,
            grade_levels=[self.grade_jss1],
            question_type=QuestionType.SINGLE_CHOICE,
            text="Scoped key",
            created_by=self.teacher_1,
            options=[{"text": "Yes", "is_correct": True}, {"text": "No", "is_correct": False}],
        )

        self.client.force_authenticate(user=self.teacher_user_1)
        allowed = self.client.get(f"/api/cbt/questions/{question.pk}/")
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)
        self.assertIn("is_correct", str(allowed.data))

        self.client.force_authenticate(user=self.teacher_user_2)
        self.assertEqual(
            self.client.get(f"/api/cbt/questions/{question.pk}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )

        self.client.force_authenticate(user=self.admin_user)
        self.assertEqual(
            self.client.get(f"/api/cbt/questions/{question.pk}/").status_code,
            status.HTTP_200_OK,
        )
