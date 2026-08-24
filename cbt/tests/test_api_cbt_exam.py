from rest_framework import status
from academic.models import (
    AcademicWorkflow,
    ApprovalRoute,
    AcademicLeadershipRole,
)
from academic.services import (
    AcademicApprovalPolicyService,
    AcademicLeadershipService,
)
from cbt.services import QuestionBankService
from cbt.models import (
    CBTExam,
    CBTExamStatus,
    ExamBlueprint,
    BlueprintRule,
    QuestionType,
    QuestionStatus,
)
from cbt.tests.base import CBTAPITestBase


class CBTExamAPITests(CBTAPITestBase):
    def test_allocated_teacher_can_create_exam(self):
        """Teacher 1 (allocated to Math in JSS 1) can create an exam."""
        self.client.force_authenticate(user=self.teacher_user_1)
        payload = {
            "title": "Math Midterm CBT",
            "session": self.session.id,
            "component": self.component.id,
            "subject": self.subj_math.id,
            "classroom": self.classroom_jss1.id,
            "duration_minutes": 45,
            "pass_mark": "50.00",
        }
        res = self.client.post("/api/cbt/exams/", data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["status"], CBTExamStatus.DRAFT)
        self.assertEqual(res.data["created_by_name"], "Alice Teacher")

    def test_unrelated_teacher_cannot_create_exam(self):
        """Teacher 2 (not allocated to Math in JSS 1) is rejected from creating Math exam in JSS 1."""
        self.client.force_authenticate(user=self.teacher_user_2)
        payload = {
            "title": "Unauthorized Math CBT",
            "session": self.session.id,
            "component": self.component.id,
            "subject": self.subj_math.id,
            "classroom": self.classroom_jss1.id,
            "duration_minutes": 45,
        }
        res = self.client.post("/api/cbt/exams/", data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_teacher_can_manage_draft_blueprint(self):
        """Teacher can get/update blueprint and add rules while exam is DRAFT."""
        exam = CBTExam.objects.create(
            session=self.session,
            component=self.component,
            subject=self.subj_math,
            classroom=self.classroom_jss1,
            title="Algebra Test",
            duration_minutes=30,
            status=CBTExamStatus.DRAFT,
            created_by=self.teacher_1,
        )

        self.client.force_authenticate(user=self.teacher_user_1)

        # GET blueprint
        res_bp = self.client.get(f"/api/cbt/exams/{exam.id}/blueprint/")
        self.assertEqual(res_bp.status_code, status.HTTP_200_OK)

        # Add rule
        rule_payload = {
            "topic": self.topic_algebra.id,
            "question_type": QuestionType.MULTIPLE_CHOICE,
            "question_count": 5,
            "marks_per_question": "2.00",
        }
        res_rule = self.client.post(
            f"/api/cbt/exams/{exam.id}/blueprint/rules/",
            data=rule_payload,
            format="json",
        )
        self.assertEqual(res_rule.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_rule.data["question_count"], 5)

    def test_generate_and_publish_flow(self):
        """Generate questions from blueprint -> READY -> Publish by HOD -> PUBLISHED."""
        # 1. Create an approved question in the bank
        q = QuestionBankService.create_question(
            subject=self.subj_math,
            grade_levels=[self.grade_jss1],
            topic=self.topic_algebra,
            question_type=QuestionType.MULTIPLE_CHOICE,
            text="Solve 3x = 12",
            created_by=self.teacher_1,
            options=[
                {"text": "x = 4", "is_correct": True},
                {"text": "x = 3", "is_correct": False},
            ],
        )
        q.status = QuestionStatus.APPROVED
        q.save(update_fields=["status"])

        # 2. Exam and Blueprint
        exam = CBTExam.objects.create(
            session=self.session,
            component=self.component,
            subject=self.subj_math,
            classroom=self.classroom_jss1,
            title="Algebra Exam",
            duration_minutes=30,
            status=CBTExamStatus.DRAFT,
            created_by=self.teacher_1,
        )
        blueprint = ExamBlueprint.objects.create(cbt_exam=exam)
        BlueprintRule.objects.create(
            blueprint=blueprint,
            topic=self.topic_algebra,
            question_type=QuestionType.MULTIPLE_CHOICE,
            question_count=1,
        )

        self.client.force_authenticate(user=self.teacher_user_1)

        # Validate blueprint
        res_val = self.client.post(f"/api/cbt/exams/{exam.id}/validate-blueprint/")
        self.assertEqual(res_val.status_code, status.HTTP_200_OK)
        self.assertTrue(res_val.data["valid"])

        # Generate exam
        res_gen = self.client.post(f"/api/cbt/exams/{exam.id}/generate/")
        self.assertEqual(res_gen.status_code, status.HTTP_200_OK)
        exam.refresh_from_db()
        self.assertEqual(exam.status, CBTExamStatus.READY)
        self.assertEqual(exam.exam_questions.count(), 1)

        # 3. Publish policy & HOD assignment
        AcademicApprovalPolicyService.set_route(
            workflow=AcademicWorkflow.CBT_PUBLISH,
            approval_route=ApprovalRoute.ACADEMIC_LEADER_OR_ADMIN,
            actor=self.admin_user,
        )
        AcademicLeadershipService.assign_hod(
            teacher=self.teacher_2,
            department=self.dept_science,
            academic_year=self.academic_year,
            actor=self.admin_user,
        )

        # Non-HOD teacher cannot publish
        self.client.force_authenticate(user=self.teacher_user_1)
        res_unauth = self.client.post(f"/api/cbt/exams/{exam.id}/publish/")
        self.assertEqual(res_unauth.status_code, status.HTTP_403_FORBIDDEN)

        # HOD publishes -> Success
        self.client.force_authenticate(user=self.teacher_user_2)
        res_pub = self.client.post(f"/api/cbt/exams/{exam.id}/publish/")
        self.assertEqual(res_pub.status_code, status.HTTP_200_OK)
        exam.refresh_from_db()
        self.assertEqual(exam.status, CBTExamStatus.PUBLISHED)

    def test_reset_to_draft(self):
        """Ready exam can be reset to draft via API."""
        exam = CBTExam.objects.create(
            session=self.session,
            component=self.component,
            subject=self.subj_math,
            classroom=self.classroom_jss1,
            title="Reset Exam Test",
            duration_minutes=30,
            status=CBTExamStatus.READY,
            created_by=self.teacher_1,
        )
        blueprint = ExamBlueprint.objects.create(cbt_exam=exam, is_locked=True)

        self.client.force_authenticate(user=self.teacher_user_1)
        res = self.client.post(f"/api/cbt/exams/{exam.id}/reset-to-draft/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        exam.refresh_from_db()
        self.assertEqual(exam.status, CBTExamStatus.DRAFT)
        blueprint.refresh_from_db()
        self.assertFalse(blueprint.is_locked)
