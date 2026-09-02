from rest_framework import status
from cbt.services import QuestionBankService
from cbt.models import (
    CBTExam,
    CBTExamStatus,
    ExamQuestion,
    QuestionType,
    QuestionStatus,
    ExamAttempt,
    ExamAttemptStatus,
)
from cbt.tests.base import CBTAPITestBase


class StudentAttemptAPITests(CBTAPITestBase):
    def setUp(self):
        super().setUp()

        # Create published exam in student's classroom (JSS 1)
        self.exam_jss1 = CBTExam.objects.create(
            session=self.session,
            component=self.component,
            subject=self.subj_math,
            classroom=self.classroom_jss1,
            title="JSS1 Math Exam",
            duration_minutes=30,
            status=CBTExamStatus.PUBLISHED,
            created_by=self.teacher_1,
        )

        # Create published exam in other classroom (JSS 2)
        self.exam_jss2 = CBTExam.objects.create(
            session=self.session,
            component=self.component,
            subject=self.subj_math,
            classroom=self.classroom_jss2,
            title="JSS2 Math Exam",
            duration_minutes=30,
            status=CBTExamStatus.PUBLISHED,
            created_by=self.teacher_1,
        )

        # Draft exam in JSS1 (should not be visible to students)
        self.exam_draft = CBTExam.objects.create(
            session=self.session,
            component=self.component,
            subject=self.subj_physics,
            classroom=self.classroom_jss1,
            title="Draft Physics Exam",
            duration_minutes=30,
            status=CBTExamStatus.DRAFT,
            created_by=self.teacher_1,
        )

        # Questions for JSS1 exam
        self.q1 = QuestionBankService.create_question(
            subject=self.subj_math,
            grade_levels=[self.grade_jss1],
            topic=self.topic_algebra,
            question_type=QuestionType.MULTIPLE_CHOICE,
            text="Question 1 text",
            created_by=self.teacher_1,
            options=[
                {"text": "Option A (Correct)", "is_correct": True},
                {"text": "Option B", "is_correct": False},
            ],
        )
        self.q1.status = QuestionStatus.APPROVED
        self.q1.save(update_fields=["status"])

        self.eq1 = ExamQuestion.objects.create(
            cbt_exam=self.exam_jss1,
            question_version=self.q1.current_version,
            order=1,
            marks=10,
        )

    def test_student_lists_only_eligible_published_exams(self):
        """Student sees only PUBLISHED exams in their active enrolled classroom."""
        self.client.force_authenticate(user=self.student_user)
        res = self.client.get("/api/cbt/student/exams/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        exam_ids = [e["id"] for e in res.data["results"] if isinstance(res.data, dict) and "results" in res.data] or [e["id"] for e in res.data]
        self.assertIn(self.exam_jss1.id, exam_ids)
        self.assertNotIn(self.exam_jss2.id, exam_ids)
        self.assertNotIn(self.exam_draft.id, exam_ids)

    def test_student_start_and_resume_attempt(self):
        """Student starts exam attempt and receives attempt payload with shuffled ordering."""
        self.client.force_authenticate(user=self.student_user)

        # Start attempt
        res_start = self.client.post(f"/api/cbt/student/exams/{self.exam_jss1.id}/start/")
        self.assertEqual(res_start.status_code, status.HTTP_201_CREATED)
        attempt_id = res_start.data["id"]
        self.assertEqual(res_start.data["status"], ExamAttemptStatus.IN_PROGRESS)
        self.assertEqual(res_start.data["total_questions"], 1)

        # Check question safe representation
        q_data = res_start.data["questions"][0]
        self.assertEqual(q_data["display_order"], 1)
        self.assertEqual(q_data["question_text"], "Question 1 text")

        # Zero answer keys in options
        for opt in q_data["options"]:
            self.assertNotIn("is_correct", opt)
            self.assertIn("option_id", opt)
            self.assertIn("text", opt)

        # Resume attempt via retrieve
        res_resume = self.client.get(f"/api/cbt/student/attempts/{attempt_id}/")
        self.assertEqual(res_resume.status_code, status.HTTP_200_OK)
        self.assertEqual(res_resume.data["id"], attempt_id)

    def test_duplicate_attempt_start_resumes_existing_attempt(self):
        """Retrying start returns the same active attempt."""
        self.client.force_authenticate(user=self.student_user)
        res1 = self.client.post(f"/api/cbt/student/exams/{self.exam_jss1.id}/start/")
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        res2 = self.client.post(f"/api/cbt/student/exams/{self.exam_jss1.id}/start/")
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res2.data["id"], res1.data["id"])
        self.assertEqual(res2.data["public_id"], res1.data["public_id"])

    def test_cross_student_attempt_isolation(self):
        """A student cannot access another student's exam attempt."""
        self.client.force_authenticate(user=self.student_user)
        res_start = self.client.post(f"/api/cbt/student/exams/{self.exam_jss1.id}/start/")
        attempt_id = res_start.data["id"]

        # Other student tries to retrieve
        self.client.force_authenticate(user=self.other_student_user)
        res_unauth = self.client.get(f"/api/cbt/student/attempts/{attempt_id}/")
        self.assertEqual(res_unauth.status_code, status.HTTP_404_NOT_FOUND)
