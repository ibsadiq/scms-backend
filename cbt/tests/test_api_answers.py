from rest_framework import status
from cbt.services import QuestionBankService
from cbt.models import (
    CBTExam,
    CBTExamStatus,
    ExamQuestion,
    QuestionType,
    QuestionStatus,
    ExamAttemptStatus,
)
from cbt.tests.base import CBTAPITestBase


class AnswerAPITests(CBTAPITestBase):
    def setUp(self):
        super().setUp()

        self.exam = CBTExam.objects.create(
            session=self.session,
            component=self.component,
            subject=self.subj_math,
            classroom=self.classroom_jss1,
            title="Math Answers CBT",
            duration_minutes=30,
            status=CBTExamStatus.PUBLISHED,
            created_by=self.teacher_1,
        )

        # Choice question
        self.q_choice = QuestionBankService.create_question(
            subject=self.subj_math,
            grade_levels=[self.grade_jss1],
            question_type=QuestionType.SINGLE_CHOICE,
            text="What is 5 + 5?",
            created_by=self.teacher_1,
            options=[
                {"text": "10", "is_correct": True},
                {"text": "11", "is_correct": False},
            ],
        )
        self.q_choice.status = QuestionStatus.APPROVED
        self.q_choice.save(update_fields=["status"])
        self.eq1 = ExamQuestion.objects.create(
            cbt_exam=self.exam,
            question_version=self.q_choice.current_version,
            order=1,
            marks=5,
        )

        # Short answer question
        self.q_text = QuestionBankService.create_question(
            subject=self.subj_math,
            grade_levels=[self.grade_jss1],
            question_type=QuestionType.SHORT_ANSWER,
            text="State the value of pi to 2 decimals.",
            created_by=self.teacher_1,
            answer_definition={"accepted_variants": ["3.14"]},
        )
        self.q_text.status = QuestionStatus.APPROVED
        self.q_text.save(update_fields=["status"])
        self.eq2 = ExamQuestion.objects.create(
            cbt_exam=self.exam,
            question_version=self.q_text.current_version,
            order=2,
            marks=5,
        )

    def test_save_and_clear_and_flag_answers(self):
        """Save choice answer, text answer, clear answer, and flag question."""
        self.client.force_authenticate(user=self.student_user)

        # Start attempt
        res_start = self.client.post(f"/api/cbt/student/exams/{self.exam.id}/start/")
        attempt_id = res_start.data["id"]
        questions = res_start.data["questions"]
        aq1_id = questions[0]["id"]
        aq2_id = questions[1]["id"]
        opt_id = questions[0]["options"][0]["option_id"]

        # 1. Save single choice answer
        res_ans1 = self.client.put(
            f"/api/cbt/attempt-questions/{aq1_id}/answer/",
            data={"option_ids": [opt_id]},
            format="json",
        )
        self.assertEqual(res_ans1.status_code, status.HTTP_200_OK)
        self.assertEqual(
            res_ans1.data["question"]["student_response"]["option_ids"], [opt_id]
        )

        # 2. Save text answer
        res_ans2 = self.client.put(
            f"/api/cbt/attempt-questions/{aq2_id}/answer/",
            data={"text": "3.14"},
            format="json",
        )
        self.assertEqual(res_ans2.status_code, status.HTTP_200_OK)
        self.assertEqual(
            res_ans2.data["question"]["student_response"]["text"], "3.14"
        )

        # 3. Flag question 1
        res_flag = self.client.patch(
            f"/api/cbt/attempt-questions/{aq1_id}/flag/",
            data={"flagged": True},
            format="json",
        )
        self.assertEqual(res_flag.status_code, status.HTTP_200_OK)
        self.assertTrue(res_flag.data["question"]["is_flagged"])

        # 4. Clear answer on question 2
        res_clear = self.client.delete(f"/api/cbt/attempt-questions/{aq2_id}/answer/")
        self.assertEqual(res_clear.status_code, status.HTTP_200_OK)
        self.assertIsNone(res_clear.data["question"]["student_response"])

        # 5. Submit attempt
        res_sub = self.client.post(f"/api/cbt/student/attempts/{attempt_id}/submit/")
        self.assertEqual(res_sub.status_code, status.HTTP_200_OK)
        self.assertEqual(res_sub.data["attempt"]["status"], ExamAttemptStatus.SUBMITTED)

        # 6. Cannot modify answer after submission
        res_after = self.client.put(
            f"/api/cbt/attempt-questions/{aq1_id}/answer/",
            data={"option_ids": [opt_id]},
            format="json",
        )
        self.assertEqual(res_after.status_code, status.HTTP_400_BAD_REQUEST)
