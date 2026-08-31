from rest_framework import status
from cbt.services import QuestionBankService
from cbt.models import (
    CBTExam,
    CBTExamStatus,
    ExamQuestion,
    QuestionType,
    QuestionStatus,
    ExamAttemptStatus,
    AttemptGradingStatus,
    QuestionGradingStatus,
    AttemptGrade,
)
from cbt.tests.base import CBTAPITestBase
from examination.models import AssessmentEntry


class GradingAndPostingAPITests(CBTAPITestBase):
    def setUp(self):
        super().setUp()

        # Exam with 1 Essay question
        self.exam = CBTExam.objects.create(
            session=self.session,
            component=self.component,
            subject=self.subj_math,
            classroom=self.classroom_jss1,
            title="Essay Math Exam",
            duration_minutes=30,
            status=CBTExamStatus.PUBLISHED,
            created_by=self.teacher_1,
        )

        self.q_essay = QuestionBankService.create_question(
            subject=self.subj_math,
            grade_levels=[self.grade_jss1],
            question_type=QuestionType.ESSAY,
            text="Explain the Pythagorean theorem.",
            created_by=self.teacher_1,
            answer_definition={"rubric": "State a^2 + b^2 = c^2"},
        )
        self.q_essay.status = QuestionStatus.APPROVED
        self.q_essay.save(update_fields=["status"])

        self.eq = ExamQuestion.objects.create(
            cbt_exam=self.exam,
            question_version=self.q_essay.current_version,
            order=1,
            marks=10,
        )

    def test_manual_essay_grading_and_result_posting_flow(self):
        """Student submits essay -> Teacher grades essay via API -> Teacher posts result."""
        # 1. Student takes and submits exam
        self.client.force_authenticate(user=self.student_user)
        res_start = self.client.post(f"/api/cbt/student/exams/{self.exam.id}/start/")
        attempt_id = res_start.data["id"]
        aq_id = res_start.data["questions"][0]["id"]

        self.client.put(
            f"/api/cbt/attempt-questions/{aq_id}/answer/",
            data={"text": "In a right triangle, the square of the hypotenuse equals the sum of squares of legs."},
            format="json",
        )
        self.client.post(f"/api/cbt/student/attempts/{attempt_id}/submit/")

        # Check grade status is NEEDS_MANUAL
        grade = AttemptGrade.objects.get(attempt_id=attempt_id)
        self.assertEqual(grade.status, AttemptGradingStatus.NEEDS_MANUAL)

        # 2. Teacher views manual grading queue
        self.client.force_authenticate(user=self.teacher_user_1)
        res_queue = self.client.get("/api/cbt/grading/manual/pending/")
        self.assertEqual(res_queue.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_queue.data), 1)
        self.assertEqual(res_queue.data[0]["attempt_question_id"], aq_id)

        # 3. Teacher grades essay
        res_grade = self.client.post(
            f"/api/cbt/grading/manual/{aq_id}/grade/",
            data={"marks": "9.00", "feedback": "Well explained."},
            format="json",
        )
        self.assertEqual(res_grade.status_code, status.HTTP_200_OK)
        self.assertEqual(res_grade.data["awarded_marks"], "9.00")
        self.assertEqual(res_grade.data["status"], QuestionGradingStatus.MANUALLY_GRADED)

        grade.refresh_from_db()
        self.assertEqual(grade.status, AttemptGradingStatus.GRADED)
        self.assertEqual(grade.raw_score, 9.00)

        # 4. Teacher posts result
        res_post = self.client.post(f"/api/cbt/attempt-grades/{grade.id}/post-result/")
        self.assertEqual(res_post.status_code, status.HTTP_200_OK)
        entry = AssessmentEntry.objects.get(pk=res_post.data["assessment_entry_id"])
        self.assertEqual(entry.source_reference, f"cbt-attempt:{attempt_id}")
        repeated = self.client.post(f"/api/cbt/attempt-grades/{grade.id}/post-result/")
        self.assertEqual(repeated.data["assessment_entry_id"], entry.id)
        grade.refresh_from_db()
        self.assertIsNotNone(grade.posted_at)

        # 5. Student cannot post result
        self.client.force_authenticate(user=self.student_user)
        res_unauth = self.client.post(f"/api/cbt/attempt-grades/{grade.id}/post-result/")
        self.assertEqual(res_unauth.status_code, status.HTTP_403_FORBIDDEN)
