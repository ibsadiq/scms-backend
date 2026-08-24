from rest_framework import status
from academic.models import (
    AcademicWorkflow,
    ApprovalRoute,
    AcademicLeadershipRole,
    AcademicLeadershipAssignment,
)
from academic.services import AcademicApprovalPolicyService, AcademicLeadershipService
from cbt.models import (
    Question,
    QuestionType,
    QuestionStatus,
    QuestionReview,
)
from cbt.tests.base import CBTAPITestBase


class QuestionBankAPITests(CBTAPITestBase):
    def test_teacher_can_create_question(self):
        """Teacher can create a question through DRF API."""
        self.client.force_authenticate(user=self.teacher_user_1)
        payload = {
            "subject": self.subj_math.id,
            "grade_levels": [self.grade_jss1.id],
            "topic": self.topic_algebra.id,
            "question_type": QuestionType.MULTIPLE_CHOICE,
            "text": "What is 2x + 4 = 10?",
            "default_marks": "2.00",
            "options": [
                {"text": "x = 3", "is_correct": True},
                {"text": "x = 2", "is_correct": False},
            ],
        }
        response = self.client.post("/api/cbt/questions/", data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["text"], "What is 2x + 4 = 10?")
        self.assertEqual(response.data["status"], QuestionStatus.DRAFT)

        question = Question.objects.get(pk=response.data["id"])
        self.assertEqual(question.created_by, self.teacher_1)

    def test_student_cannot_access_question_management(self):
        """Student cannot create or access question bank APIs."""
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get("/api/cbt/questions/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        payload = {
            "subject": self.subj_math.id,
            "question_type": QuestionType.SHORT_ANSWER,
            "text": "Unauthorized student question",
        }
        response = self.client.post("/api/cbt/questions/", data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_question_create_uses_service_validation(self):
        """Service-level validations (e.g. true/false requires 2 options) are enforced."""
        self.client.force_authenticate(user=self.teacher_user_1)
        payload = {
            "subject": self.subj_math.id,
            "grade_levels": [self.grade_jss1.id],
            "question_type": QuestionType.TRUE_FALSE,
            "text": "Is 5 a prime number?",
            "options": [
                {"text": "True", "is_correct": True},
            ],
        }
        response = self.client.post("/api/cbt/questions/", data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_question_submit_review_and_self_approval_blocked(self):
        """Question author cannot self-approve their own question."""
        self.client.force_authenticate(user=self.teacher_user_2)
        payload = {
            "subject": self.subj_math.id,
            "grade_levels": [self.grade_jss1.id],
            "question_type": QuestionType.MULTIPLE_CHOICE,
            "text": "What is x if x^2 = 16?",
            "options": [
                {"text": "4", "is_correct": True},
                {"text": "3", "is_correct": False},
            ],
        }
        res = self.client.post("/api/cbt/questions/", data=payload, format="json")
        question_id = res.data["id"]

        # Submit for review
        res_submit = self.client.post(f"/api/cbt/questions/{question_id}/submit-review/")
        self.assertEqual(res_submit.status_code, status.HTTP_200_OK)
        self.assertEqual(res_submit.data["status"], QuestionStatus.IN_REVIEW)

        # Author attempts to approve -> Blocked
        res_approve = self.client.post(f"/api/cbt/questions/{question_id}/approve/")
        self.assertEqual(res_approve.status_code, status.HTTP_403_FORBIDDEN)

    def test_hod_can_approve_scoped_question(self):
        """HOD can approve questions within their department."""
        AcademicApprovalPolicyService.set_route(
            workflow=AcademicWorkflow.QUESTION_BANK,
            approval_route=ApprovalRoute.ACADEMIC_LEADER_OR_ADMIN,
            actor=self.admin_user,
        )
        AcademicLeadershipService.assign_hod(
            teacher=self.teacher_1,
            department=self.dept_science,
            academic_year=self.academic_year,
            actor=self.admin_user,
        )

        # Teacher 2 creates and submits
        self.client.force_authenticate(user=self.teacher_user_2)
        payload = {
            "subject": self.subj_math.id,
            "grade_levels": [self.grade_jss1.id],
            "question_type": QuestionType.MULTIPLE_CHOICE,
            "text": "What is 3 + 7?",
            "options": [
                {"text": "10", "is_correct": True},
                {"text": "9", "is_correct": False},
            ],
        }
        res = self.client.post("/api/cbt/questions/", data=payload, format="json")
        q_id = res.data["id"]
        self.client.post(f"/api/cbt/questions/{q_id}/submit-review/")

        # HOD (Teacher 1) approves
        self.client.force_authenticate(user=self.teacher_user_1)
        res_approve = self.client.post(
            f"/api/cbt/questions/{q_id}/approve/",
            data={"comments": "Approved by HOD"},
            format="json",
        )
        self.assertEqual(res_approve.status_code, status.HTTP_200_OK)
        self.assertEqual(res_approve.data["status"], QuestionStatus.APPROVED)

        # Review record saved
        q = Question.objects.get(pk=q_id)
        review = QuestionReview.objects.filter(question_version=q.current_version).first()
        self.assertIsNotNone(review)
        self.assertEqual(review.reviewed_by, self.teacher_1)

    def test_admin_can_approve_question(self):
        """School admin can approve questions."""
        self.client.force_authenticate(user=self.teacher_user_1)
        payload = {
            "subject": self.subj_math.id,
            "grade_levels": [self.grade_jss1.id],
            "question_type": QuestionType.SHORT_ANSWER,
            "text": "Name the capital of Nigeria.",
            "answer_definition": {"accepted_answers": ["Abuja"]},
        }
        res = self.client.post("/api/cbt/questions/", data=payload, format="json")
        q_id = res.data["id"]
        res_submit = self.client.post(f"/api/cbt/questions/{q_id}/submit-review/")
        self.assertEqual(res_submit.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=self.admin_user)
        res_approve = self.client.post(f"/api/cbt/questions/{q_id}/approve/")
        self.assertEqual(res_approve.status_code, status.HTTP_200_OK)
        self.assertEqual(res_approve.data["status"], QuestionStatus.APPROVED)

    def test_question_new_version(self):
        """Teacher can create a new version of an approved question, returning it to draft."""
        self.client.force_authenticate(user=self.teacher_user_1)
        payload = {
            "subject": self.subj_math.id,
            "grade_levels": [self.grade_jss1.id],
            "question_type": QuestionType.SHORT_ANSWER,
            "text": "Original version",
            "answer_definition": {"accepted_variants": ["ans"]},
        }
        res = self.client.post("/api/cbt/questions/", data=payload, format="json")
        q_id = res.data["id"]
        self.client.post(f"/api/cbt/questions/{q_id}/submit-review/")

        self.client.force_authenticate(user=self.admin_user)
        self.client.post(f"/api/cbt/questions/{q_id}/approve/")

        # Create new version
        self.client.force_authenticate(user=self.teacher_user_1)
        new_version_payload = {
            "text": "Updated version 2 text",
            "answer_definition": {"accepted_variants": ["updated_ans"]},
        }
        res_v2 = self.client.post(
            f"/api/cbt/questions/{q_id}/new-version/",
            data=new_version_payload,
            format="json",
        )
        self.assertEqual(res_v2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_v2.data["version"], 2)

        q = Question.objects.get(pk=q_id)
        self.assertEqual(q.status, QuestionStatus.DRAFT)
        self.assertEqual(q.current_version.version, 2)
