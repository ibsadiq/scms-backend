from rest_framework import status
from cbt.services import QuestionBankService
from cbt.models import (
    CBTExam,
    CBTExamStatus,
    ExamQuestion,
    QuestionType,
    QuestionStatus,
)
from cbt.tests.base import CBTAPITestBase


class CBTSecurityAPITests(CBTAPITestBase):
    def setUp(self):
        super().setUp()

        self.exam = CBTExam.objects.create(
            session=self.session,
            component=self.component,
            subject=self.subj_math,
            classroom=self.classroom_jss1,
            title="Security Audit Exam",
            duration_minutes=30,
            status=CBTExamStatus.PUBLISHED,
            created_by=self.teacher_1,
        )

        self.q = QuestionBankService.create_question(
            subject=self.subj_math,
            grade_levels=[self.grade_jss1],
            question_type=QuestionType.MULTIPLE_CHOICE,
            text="Secret Question",
            created_by=self.teacher_1,
            options=[
                {"text": "Secret Correct Option", "is_correct": True},
                {"text": "Wrong Option", "is_correct": False},
            ],
        )
        self.q.status = QuestionStatus.APPROVED
        self.q.save(update_fields=["status"])

        self.eq = ExamQuestion.objects.create(
            cbt_exam=self.exam,
            question_version=self.q.current_version,
            order=1,
            marks=10,
        )

    def test_no_student_answer_key_leak(self):
        """Student never receives `is_correct` or canonical option ordering."""
        self.client.force_authenticate(user=self.student_user)

        # 1. Exam list / detail
        res_exam = self.client.get("/api/cbt/student/exams/")
        self.assertNotIn("blueprint", str(res_exam.data))
        self.assertNotIn("exam_questions", str(res_exam.data))

        # 2. Attempt start & retrieve
        res_start = self.client.post(f"/api/cbt/student/exams/{self.exam.id}/start/")
        self.assertEqual(res_start.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("is_correct", str(res_start.data))

        attempt_id = res_start.data["id"]
        res_retrieve = self.client.get(f"/api/cbt/student/attempts/{attempt_id}/")
        self.assertNotIn("is_correct", str(res_retrieve.data))

    def test_no_unpublished_exam_access(self):
        """Student cannot start an exam in DRAFT or READY status."""
        draft_exam = CBTExam.objects.create(
            session=self.session,
            component=self.component,
            subject=self.subj_physics,
            classroom=self.classroom_jss1,
            title="Draft Physics Exam",
            duration_minutes=30,
            status=CBTExamStatus.DRAFT,
            created_by=self.teacher_1,
        )
        self.client.force_authenticate(user=self.student_user)
        res = self.client.post(f"/api/cbt/student/exams/{draft_exam.id}/start/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_unrelated_teacher_cannot_grade_essay(self):
        """Teacher 2 (not allocated to Math in JSS1) cannot grade Math essays in JSS1."""
        self.client.force_authenticate(user=self.student_user)
        res_start = self.client.post(f"/api/cbt/student/exams/{self.exam.id}/start/")
        aq_id = res_start.data["questions"][0]["id"]

        self.client.force_authenticate(user=self.teacher_user_2)
        res_grade = self.client.post(
            f"/api/cbt/grading/manual/{aq_id}/grade/",
            data={"marks": "5.00"},
            format="json",
        )
        self.assertEqual(res_grade.status_code, status.HTTP_403_FORBIDDEN)
