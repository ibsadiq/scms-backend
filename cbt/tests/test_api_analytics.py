from rest_framework import status
from django.utils import timezone
from datetime import timedelta

from cbt.models import (
    CBTExam,
    CBTExamStatus,
    ExamAttempt,
    ExamAttemptStatus,
    AttemptStartSource,
    AttemptGrade,
    AttemptGradingStatus,
    ExamQuestion,
    QuestionType,
    QuestionDifficulty,
    Question,
    QuestionVersion,
    QuestionStatus,
    QuestionOption,
    AttemptQuestion,
    AttemptQuestionGrade,
    QuestionGradingStatus,
    GradingMethod,
    StudentAnswer,
)
from cbt.tests.base import CBTAPITestBase


class CBTAnalyticsAPITests(CBTAPITestBase):
    def setUp(self):
        super().setUp()
        now = timezone.now()

        # Create published exam
        self.exam = CBTExam.objects.create(
            session=self.session,
            component=self.component,
            subject=self.subj_math,
            classroom=self.classroom_jss1,
            duration_minutes=60,
            status=CBTExamStatus.PUBLISHED,
            created_by=self.teacher_1,
        )

        # Create question in bank & exam
        self.q = Question.objects.create(
            subject=self.subj_math,
            question_type=QuestionType.SINGLE_CHOICE,
            difficulty=QuestionDifficulty.MEDIUM,
            topic=self.topic_algebra,
            status=QuestionStatus.APPROVED,
            default_marks=10,
        )
        self.qv = QuestionVersion.objects.create(
            question=self.q,
            version=1,
            question_type=QuestionType.SINGLE_CHOICE,
            text="What is 2 + 2?",
            created_by=self.teacher_1,
            default_marks=10,
        )
        self.opt1 = QuestionOption.objects.create(
            question_version=self.qv,
            text="4",
            is_correct=True,
            order=1,
        )
        self.opt2 = QuestionOption.objects.create(
            question_version=self.qv,
            text="5",
            is_correct=False,
            order=2,
        )
        self.eq = ExamQuestion.objects.create(
            cbt_exam=self.exam,
            question_version=self.qv,
            marks=10,
            order=1,
        )

        # Create attempt and graded result for student
        self.attempt = ExamAttempt.objects.create(
            cbt_exam=self.exam,
            student=self.student,
            enrollment=self.enrollment,
            start_source=AttemptStartSource.ONLINE,
            status=ExamAttemptStatus.SUBMITTED,
            started_at=now - timedelta(minutes=45),
            expires_at=now + timedelta(minutes=15),
            submitted_at=now - timedelta(minutes=5),
        )

        self.aq = AttemptQuestion.objects.create(
            attempt=self.attempt,
            exam_question=self.eq,
            display_order=1,
        )

        self.answer = StudentAnswer.objects.create(
            attempt_question=self.aq,
            is_answered=True,
            answered_at=now - timedelta(minutes=10),
        )

        self.q_grade = AttemptQuestionGrade.objects.create(
            attempt_question=self.aq,
            awarded_marks=10,
            max_marks=10,
            is_correct=True,
            status=QuestionGradingStatus.AUTO_GRADED,
            grading_method=GradingMethod.AUTO,
        )

        self.grade = AttemptGrade.objects.create(
            attempt=self.attempt,
            status=AttemptGradingStatus.GRADED,
            raw_score=10,
            total_marks=10,
            percentage=100.0,
            normalized_score=100.0,
            graded_at=now - timedelta(minutes=2),
        )

    def test_allocated_teacher_can_list_analytics_exams(self):
        """Teacher 1 (allocated to Math in JSS1) can list analytics exams."""
        self.client.force_authenticate(user=self.teacher_user_1)
        res = self.client.get("/api/cbt/analytics/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        exam_ids = [e["id"] for e in results]
        self.assertIn(self.exam.id, exam_ids)

    def test_unrelated_teacher_cannot_access_analytics(self):
        """Teacher 2 (unrelated to Math in JSS1) cannot view analytics for this exam."""
        self.client.force_authenticate(user=self.teacher_user_2)
        res = self.client.get(f"/api/cbt/analytics/{self.exam.id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_student_cannot_access_analytics(self):
        """Students are strictly rejected from staff performance analytics."""
        self.client.force_authenticate(user=self.student_user)
        res = self.client.get(f"/api/cbt/analytics/{self.exam.id}/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_exam_analytics_retrieval_and_distribution(self):
        """Allocated teacher receives comprehensive summary, score distribution, and items."""
        self.client.force_authenticate(user=self.teacher_user_1)
        res = self.client.get(f"/api/cbt/analytics/{self.exam.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        data = res.data
        self.assertIn("summary", data)
        self.assertIn("score_distribution", data)
        self.assertIn("questions", data)
        self.assertIn("aggregations", data)
        self.assertIn("candidates", data)

        # Check summary metrics
        self.assertEqual(data["summary"]["graded_count"], 1)
        self.assertEqual(data["summary"]["average_score"], 100.0)

        # Check score distribution
        dist = data["score_distribution"]
        self.assertEqual(len(dist), 10)
        top_bucket = next(b for b in dist if b["band"] == "90–100%")
        self.assertEqual(top_bucket["count"], 1)

        # Check questions list
        questions = data["questions"]
        self.assertEqual(len(questions), 1)
        q1 = questions[0]
        self.assertEqual(q1["order"], 1)
        self.assertEqual(q1["average_percentage"], 100.0)
        self.assertEqual(q1["facility_index"], 1.0)
        self.assertEqual(q1["full_credit_rate"], 100.0)
