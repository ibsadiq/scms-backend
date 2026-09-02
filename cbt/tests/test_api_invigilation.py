from rest_framework import status
from django.utils import timezone
from datetime import timedelta

from cbt.models import (
    CBTExam,
    CBTExamStatus,
    ExamAttempt,
    ExamAttemptStatus,
    AttemptStartSource,
    AttemptQuestion,
)
from cbt.tests.base import CBTAPITestBase


class CBTInvigilationAPITests(CBTAPITestBase):
    def setUp(self):
        super().setUp()
        # Create a published exam for Math in classroom_jss1
        self.exam = CBTExam.objects.create(
            session=self.session,
            component=self.component,
            subject=self.subj_math,
            classroom=self.classroom_jss1,
            duration_minutes=60,
            status=CBTExamStatus.PUBLISHED,
            created_by=self.teacher_1,
        )

        now = timezone.now()
        # Create an attempt for student_user
        self.attempt = ExamAttempt.objects.create(
            cbt_exam=self.exam,
            student=self.student,
            enrollment=self.enrollment,
            start_source=AttemptStartSource.ONLINE,
            status=ExamAttemptStatus.IN_PROGRESS,
            started_at=now,
            expires_at=now + timedelta(minutes=60),
            last_activity_at=now + timedelta(minutes=5),
        )

    def test_allocated_teacher_can_list_monitorable_exams(self):
        """Teacher 1 (allocated to Math in JSS1) can list monitorable exams."""
        self.client.force_authenticate(user=self.teacher_user_1)
        res = self.client.get("/api/cbt/invigilation/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Should include self.exam
        results = res.data.get("results", res.data)
        exam_ids = [e["id"] for e in results]
        self.assertIn(self.exam.id, exam_ids)

        # Check telemetry metrics
        target = next(e for e in results if e["id"] == self.exam.id)
        self.assertEqual(target["started_count"], 1)
        self.assertEqual(target["in_progress_count"], 1)
        self.assertEqual(target["submitted_count"], 0)

    def test_unrelated_teacher_cannot_see_exam_in_invigilation(self):
        """Teacher 2 (not allocated to Math in JSS1) cannot monitor this exam."""
        self.client.force_authenticate(user=self.teacher_user_2)
        res = self.client.get("/api/cbt/invigilation/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        exam_ids = [e["id"] for e in results]
        self.assertNotIn(self.exam.id, exam_ids)

    def test_student_is_denied_access_to_invigilation(self):
        """Students cannot access staff invigilation endpoints."""
        self.client.force_authenticate(user=self.student_user)
        res = self.client.get("/api/cbt/invigilation/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_allocated_teacher_can_list_candidate_attempts(self):
        """Teacher 1 can inspect candidate attempts for the exam."""
        self.client.force_authenticate(user=self.teacher_user_1)
        res = self.client.get(f"/api/cbt/invigilation/{self.exam.id}/attempts/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        attempt_data = res.data[0]
        self.assertEqual(attempt_data["public_id"], str(self.attempt.public_id))
        self.assertEqual(attempt_data["status"], ExamAttemptStatus.IN_PROGRESS)
        self.assertEqual(attempt_data["start_source"], AttemptStartSource.ONLINE)

    def test_allocated_teacher_can_get_single_attempt_telemetry(self):
        """Teacher 1 can view deep telemetry for a candidate attempt without answer key leakage."""
        self.client.force_authenticate(user=self.teacher_user_1)
        res = self.client.get(f"/api/cbt/invigilation/attempts/{self.attempt.public_id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["public_id"], str(self.attempt.public_id))
        self.assertIn("questions_progress", res.data)
        self.assertIn("events_summary", res.data)
        # Ensure private answer keys are NOT in telemetry
        self.assertNotIn("correct_option", str(res.data))
        self.assertNotIn("model_answer", str(res.data))
