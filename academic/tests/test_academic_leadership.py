from school.testcases import TenantTestCase as TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone

from academic.models import (
    Department,
    Subject,
    Teacher,
    GradeLevel,
    ClassRoom,
    Curriculum,
    CurriculumSubject,
    Topic,
    SubTopic,
    CurriculumTopic,
    LearningObjective,
    SchemeOfWork,
    SchemeOfWorkStatus,
    SchemeOfWorkItem,
    AllocatedSubject,
    LessonPlan,
    LessonPlanStatus,
    SectionType,
    AcademicLeadershipRole,
    AcademicLeadershipAssignment,
    AcademicWorkflow,
    ApprovalRoute,
    AcademicApprovalPolicy,
)
from administration.models import AcademicYear, Term
from academic.services import (
    AcademicApprovalPolicyService,
    AcademicLeadershipService,
    AcademicAuthorityService,
    SchemeOfWorkService,
    LessonPlanService,
)
from examination.models import (
    GradingScheme,
    AssessmentComponent,
    AssessmentSession,
    AssessmentType,
)
from cbt.models import (
    Question,
    QuestionType,
    QuestionVersion,
    QuestionStatus,
    QuestionOption,
    QuestionReview,
    CBTExam,
    CBTExamStatus,
    ExamQuestion,
)
from cbt.services import QuestionBankService, CBTExamService

User = get_user_model()


class AcademicLeadershipAndApprovalTests(TestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        return super().setup_tenant(tenant)

    def setUp(self):
        # 1. Users
        self.admin_user = User.objects.create_user(
            email="admin@school.com",
            password="password123",
            first_name="Admin",
            last_name="User",
            is_admin=True,
            is_staff=True,
        )
        self.teacher_user_1 = User.objects.create_user(
            email="teacher1@school.com",
            password="password123",
            first_name="Alice",
            last_name="Science",
        )
        self.teacher_user_2 = User.objects.create_user(
            email="teacher2@school.com",
            password="password123",
            first_name="Bob",
            last_name="Math",
        )
        self.teacher_user_3 = User.objects.create_user(
            email="teacher3@school.com",
            password="password123",
            first_name="Clara",
            last_name="Primary",
        )

        self.teacher_1 = Teacher.objects.create(user=self.teacher_user_1)
        self.teacher_2 = Teacher.objects.create(user=self.teacher_user_2)
        self.teacher_3 = Teacher.objects.create(user=self.teacher_user_3)

        # 2. Academic structure
        self.academic_year = AcademicYear.objects.create(
            name="2026/2027",
            start_date="2026-09-01",
            end_date="2027-07-31",
            active_year=True,
        )
        self.term = Term.objects.create(
            name="First Term",
            academic_year=self.academic_year,
            start_date="2026-09-01",
            end_date="2026-12-15",
        )

        self.dept_science = Department.objects.create(name="Sciences")
        self.dept_arts = Department.objects.create(name="Arts")

        self.subj_physics = Subject.objects.create(
            name="Physics", subject_code="PHY", department=self.dept_science
        )
        self.subj_math = Subject.objects.create(
            name="Mathematics", subject_code="MTH", department=self.dept_science
        )
        self.subj_english = Subject.objects.create(
            name="English", subject_code="ENG", department=self.dept_arts
        )

        # Grade levels
        self.grade_jss1 = GradeLevel.objects.create(
            system_code="JSS_1",
            default_name="JSS 1",
            section=SectionType.JUNIOR_SECONDARY,
            sequence_order=11,
        )
        self.grade_pri1 = GradeLevel.objects.create(
            system_code="BASIC_1",
            default_name="Basic 1",
            section=SectionType.PRIMARY,
            sequence_order=5,
        )

        self.classroom_jss1 = ClassRoom.objects.create(name="A", grade_level=self.grade_jss1)
        self.classroom_pri1 = ClassRoom.objects.create(name="A", grade_level=self.grade_pri1)

        # Curriculum
        self.curriculum = Curriculum.objects.create(name="National Curriculum")
        self.curr_sub_physics = CurriculumSubject.objects.create(
            curriculum=self.curriculum,
            grade_level=self.grade_jss1,
            subject=self.subj_physics,
        )
        self.topic_physics = Topic.objects.create(
            subject=self.subj_physics,
            grade_level=self.grade_jss1,
            name="Motion",
        )
        self.curr_topic_physics = CurriculumTopic.objects.create(
            curriculum_subject=self.curr_sub_physics,
            topic=self.topic_physics,
            order=1,
        )
        self.lo_physics = LearningObjective.objects.create(
            curriculum_topic=self.curr_topic_physics,
            description="Define velocity and acceleration",
            order=1,
        )

        # Scheme of work
        self.scheme_physics = SchemeOfWork.objects.create(
            academic_year=self.academic_year,
            term=self.term,
            curriculum_subject=self.curr_sub_physics,
            created_by=self.teacher_2,
            status=SchemeOfWorkStatus.DRAFT,
        )
        self.scheme_item_physics = SchemeOfWorkItem.objects.create(
            scheme=self.scheme_physics,
            week_number=1,
            curriculum_topic=self.curr_topic_physics,
        )
        self.scheme_item_physics.learning_objectives.add(self.lo_physics)

        # Teacher allocation
        self.alloc_physics = AllocatedSubject.objects.create(
            teacher_name=self.teacher_2,
            subject=self.subj_physics,
            class_room=self.classroom_jss1,
            academic_year=self.academic_year,
            term=self.term,
            weekly_periods=4,
        )

        # Lesson plan
        self.lesson_plan = LessonPlan.objects.create(
            scheme_item=self.scheme_item_physics,
            allocation=self.alloc_physics,
            lesson_date=timezone.now().date(),
            title="Introduction to Velocity",
            status=LessonPlanStatus.DRAFT,
        )
        self.lesson_plan.learning_objectives.add(self.lo_physics)

    def test_leadership_model_validation(self):
        """HOD requires department; Head Teacher requires section."""
        # 1. HOD without department raises ValidationError
        hod_invalid = AcademicLeadershipAssignment(
            teacher=self.teacher_1,
            role=AcademicLeadershipRole.HOD,
            department=None,
            academic_year=self.academic_year,
        )
        with self.assertRaises(ValidationError):
            hod_invalid.full_clean()

        # 2. Head Teacher without section raises ValidationError
        ht_invalid = AcademicLeadershipAssignment(
            teacher=self.teacher_3,
            role=AcademicLeadershipRole.HEAD_TEACHER,
            section=None,
            academic_year=self.academic_year,
        )
        with self.assertRaises(ValidationError):
            ht_invalid.full_clean()

        # 3. Valid HOD assignment
        hod_valid = AcademicLeadershipService.assign_hod(
            teacher=self.teacher_1,
            department=self.dept_science,
            academic_year=self.academic_year,
            actor=self.admin_user,
        )
        self.assertTrue(hod_valid.is_active)
        self.assertEqual(hod_valid.role, AcademicLeadershipRole.HOD)

        # 4. Valid Head Teacher assignment
        ht_valid = AcademicLeadershipService.assign_head_teacher(
            teacher=self.teacher_3,
            section=SectionType.PRIMARY,
            academic_year=self.academic_year,
            actor=self.admin_user,
        )
        self.assertTrue(ht_valid.is_active)
        self.assertEqual(ht_valid.role, AcademicLeadershipRole.HEAD_TEACHER)

    def test_default_policy_is_admin_only(self):
        """When no policy is created, get_route returns ADMIN_ONLY."""
        route = AcademicApprovalPolicyService.get_route(AcademicWorkflow.LESSON_PLAN)
        self.assertEqual(route, ApprovalRoute.ADMIN_ONLY)

    def test_lesson_plan_approval_admin_only_policy(self):
        """Under ADMIN_ONLY policy, non-admin HOD cannot approve; Admin can approve."""
        # Assign teacher 1 as Science HOD
        AcademicLeadershipService.assign_hod(
            teacher=self.teacher_1,
            department=self.dept_science,
            academic_year=self.academic_year,
            actor=self.admin_user,
        )

        LessonPlanService.submit(self.lesson_plan)
        self.assertEqual(self.lesson_plan.status, LessonPlanStatus.SUBMITTED)

        # HOD attempts approval under ADMIN_ONLY -> PermissionDenied
        with self.assertRaises(PermissionDenied):
            LessonPlanService.approve(self.lesson_plan, reviewed_by=self.teacher_1)

        # Admin approves -> Success
        LessonPlanService.approve(self.lesson_plan, reviewed_by=self.admin_user)
        self.lesson_plan.refresh_from_db()
        self.assertEqual(self.lesson_plan.status, LessonPlanStatus.APPROVED)

    def test_lesson_plan_approval_hod_policy(self):
        """Under ACADEMIC_LEADER_OR_ADMIN policy, Science HOD can approve Science lesson plan."""
        AcademicApprovalPolicyService.set_route(
            workflow=AcademicWorkflow.LESSON_PLAN,
            approval_route=ApprovalRoute.ACADEMIC_LEADER_OR_ADMIN,
            actor=self.admin_user,
        )

        AcademicLeadershipService.assign_hod(
            teacher=self.teacher_1,
            department=self.dept_science,
            academic_year=self.academic_year,
            actor=self.admin_user,
        )

        LessonPlanService.submit(self.lesson_plan)

        # Teacher 1 (Science HOD) approves Physics lesson plan -> Success
        LessonPlanService.approve(self.lesson_plan, reviewed_by=self.teacher_1)
        self.lesson_plan.refresh_from_db()
        self.assertEqual(self.lesson_plan.status, LessonPlanStatus.APPROVED)
        self.assertEqual(self.lesson_plan.reviewed_by, self.teacher_1)

    def test_self_approval_is_prohibited(self):
        """The creator/allocated teacher cannot approve their own lesson plan or scheme."""
        AcademicApprovalPolicyService.set_route(
            workflow=AcademicWorkflow.LESSON_PLAN,
            approval_route=ApprovalRoute.ACADEMIC_LEADER_OR_ADMIN,
            actor=self.admin_user,
        )
        # Even if Teacher 2 is HOD of Sciences, Teacher 2 created this lesson plan
        AcademicLeadershipService.assign_hod(
            teacher=self.teacher_2,
            department=self.dept_science,
            academic_year=self.academic_year,
            actor=self.admin_user,
        )

        LessonPlanService.submit(self.lesson_plan)

        with self.assertRaises(PermissionDenied):
            LessonPlanService.approve(self.lesson_plan, reviewed_by=self.teacher_2)

    def test_unrelated_hod_rejected(self):
        """Arts HOD cannot approve a Science lesson plan."""
        AcademicApprovalPolicyService.set_route(
            workflow=AcademicWorkflow.LESSON_PLAN,
            approval_route=ApprovalRoute.ACADEMIC_LEADER_OR_ADMIN,
            actor=self.admin_user,
        )
        # Assign teacher 1 to Arts HOD
        AcademicLeadershipService.assign_hod(
            teacher=self.teacher_1,
            department=self.dept_arts,
            academic_year=self.academic_year,
            actor=self.admin_user,
        )

        LessonPlanService.submit(self.lesson_plan)

        with self.assertRaises(PermissionDenied):
            LessonPlanService.approve(self.lesson_plan, reviewed_by=self.teacher_1)

    def test_scheme_of_work_lifecycle(self):
        """Test Scheme of Work submit, approve, reject, reopen_for_revision."""
        AcademicApprovalPolicyService.set_route(
            workflow=AcademicWorkflow.SCHEME_OF_WORK,
            approval_route=ApprovalRoute.ACADEMIC_LEADER_OR_ADMIN,
            actor=self.admin_user,
        )
        AcademicLeadershipService.assign_hod(
            teacher=self.teacher_1,
            department=self.dept_science,
            academic_year=self.academic_year,
            actor=self.admin_user,
        )

        # 1. Submit
        SchemeOfWorkService.submit(self.scheme_physics)
        self.scheme_physics.refresh_from_db()
        self.assertEqual(self.scheme_physics.status, SchemeOfWorkStatus.SUBMITTED)

        # 2. Reject
        SchemeOfWorkService.reject(
            self.scheme_physics,
            actor=self.teacher_1,
            reason="Please include additional learning objectives for week 1.",
        )
        self.scheme_physics.refresh_from_db()
        self.assertEqual(self.scheme_physics.status, SchemeOfWorkStatus.REJECTED)
        self.assertEqual(self.scheme_physics.reviewed_by, self.teacher_1)

        # 3. Reopen
        SchemeOfWorkService.reopen_for_revision(self.scheme_physics)
        self.scheme_physics.refresh_from_db()
        self.assertEqual(self.scheme_physics.status, SchemeOfWorkStatus.DRAFT)

        # 4. Resubmit & Approve
        SchemeOfWorkService.submit(self.scheme_physics)
        SchemeOfWorkService.approve(self.scheme_physics, actor=self.teacher_1)
        self.scheme_physics.refresh_from_db()
        self.assertEqual(self.scheme_physics.status, SchemeOfWorkStatus.APPROVED)
        self.assertEqual(self.scheme_physics.reviewed_by, self.teacher_1)

    def test_question_bank_hod_approval(self):
        """QuestionBankService calls AcademicAuthorityService."""
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

        # Author is Teacher 2
        q = QuestionBankService.create_question(
            subject=self.subj_physics,
            grade_levels=[self.grade_jss1],
            question_type=QuestionType.MULTIPLE_CHOICE,
            text="What is velocity?",
            created_by=self.teacher_2,
            options=[
                {"text": "Rate of change of displacement", "is_correct": True},
                {"text": "Rate of change of speed", "is_correct": False},
            ],
        )
        QuestionBankService.submit_for_review(q, user=self.teacher_2)
        q.refresh_from_db()
        self.assertEqual(q.status, QuestionStatus.IN_REVIEW)

        # Author cannot approve own question
        with self.assertRaises(PermissionDenied):
            QuestionBankService.approve_question(q, user=self.teacher_2, comments="Self approval")

        # Science HOD approves -> Success
        QuestionBankService.approve_question(q, user=self.teacher_1, comments="Good question.")
        q.refresh_from_db()
        self.assertEqual(q.status, QuestionStatus.APPROVED)
        self.assertTrue(QuestionReview.objects.filter(question_version=q.current_version, reviewed_by=self.teacher_1).exists())

    def test_cbt_publish_authorization(self):
        """CBTExamService.publish validates publisher authority without altering CBT statuses."""
        AcademicApprovalPolicyService.set_route(
            workflow=AcademicWorkflow.CBT_PUBLISH,
            approval_route=ApprovalRoute.ACADEMIC_LEADER_OR_ADMIN,
            actor=self.admin_user,
        )
        AcademicLeadershipService.assign_hod(
            teacher=self.teacher_1,
            department=self.dept_science,
            academic_year=self.academic_year,
            actor=self.admin_user,
        )

        session = AssessmentSession.objects.create(
            assessment_type=AssessmentType.TEST,
            name="Midterm 2026",
            academic_year=self.academic_year,
            term=self.term,
            start_date=timezone.now().date(),
            ends_date=timezone.now().date(),
            out_of=100,
        )
        grading_scheme = GradingScheme.objects.create(
            name="Standard Scheme",
            academic_year=self.academic_year,
            grade_level=self.grade_jss1,
        )
        component = AssessmentComponent.objects.create(
            scheme=grading_scheme,
            name="Exam",
            max_score=100,
            weight=100,
            order=1,
        )

        exam = CBTExam.objects.create(
            session=session,
            subject=self.subj_physics,
            classroom=self.classroom_jss1,
            component=component,
            title="Physics CBT 1",
            duration_minutes=45,
            status=CBTExamStatus.READY,
            created_by=self.teacher_2,
        )

        # Create an approved question and add to exam
        q = QuestionBankService.create_question(
            subject=self.subj_physics,
            grade_levels=[self.grade_jss1],
            question_type=QuestionType.MULTIPLE_CHOICE,
            text="What is speed?",
            created_by=self.teacher_1,
            options=[
                {"text": "Distance over time", "is_correct": True},
                {"text": "Force over area", "is_correct": False},
            ],
        )
        q.status = QuestionStatus.APPROVED
        q.save(update_fields=["status"])

        ExamQuestion.objects.create(
            cbt_exam=exam,
            question_version=q.current_version,
            order=1,
            marks=10,
        )

        # Non-HOD Teacher 3 cannot publish
        with self.assertRaises(PermissionDenied):
            CBTExamService.publish(exam=exam, actor=self.teacher_3)

        # Science HOD Teacher 1 publishes -> Success
        CBTExamService.publish(exam=exam, actor=self.teacher_1)
        exam.refresh_from_db()
        self.assertEqual(exam.status, CBTExamStatus.PUBLISHED)

    def test_head_teacher_approval_for_primary_section(self):
        """Head Teacher can approve lesson plan for primary section."""
        AcademicApprovalPolicyService.set_route(
            workflow=AcademicWorkflow.LESSON_PLAN,
            approval_route=ApprovalRoute.ACADEMIC_LEADER_OR_ADMIN,
            actor=self.admin_user,
        )
        AcademicLeadershipService.assign_head_teacher(
            teacher=self.teacher_3,
            section=SectionType.PRIMARY,
            academic_year=self.academic_year,
            actor=self.admin_user,
        )

        curr_sub_pri = CurriculumSubject.objects.create(
            curriculum=self.curriculum,
            grade_level=self.grade_pri1,
            subject=self.subj_english,
        )
        topic_pri = Topic.objects.create(
            subject=self.subj_english,
            grade_level=self.grade_pri1,
            name="Grammar",
        )
        curr_topic_pri = CurriculumTopic.objects.create(
            curriculum_subject=curr_sub_pri,
            topic=topic_pri,
            order=1,
        )
        lo_pri = LearningObjective.objects.create(
            curriculum_topic=curr_topic_pri,
            description="Nouns and Verbs",
            order=1,
        )
        scheme_pri = SchemeOfWork.objects.create(
            academic_year=self.academic_year,
            term=self.term,
            curriculum_subject=curr_sub_pri,
            created_by=self.teacher_2,
            status=SchemeOfWorkStatus.DRAFT,
        )
        scheme_item_pri = SchemeOfWorkItem.objects.create(
            scheme=scheme_pri,
            week_number=1,
            curriculum_topic=curr_topic_pri,
        )
        scheme_item_pri.learning_objectives.add(lo_pri)

        alloc_pri = AllocatedSubject.objects.create(
            teacher_name=self.teacher_2,
            subject=self.subj_english,
            class_room=self.classroom_pri1,
            academic_year=self.academic_year,
            term=self.term,
            weekly_periods=4,
        )
        plan_pri = LessonPlan.objects.create(
            scheme_item=scheme_item_pri,
            allocation=alloc_pri,
            lesson_date=timezone.now().date(),
            title="Introduction to Nouns",
            status=LessonPlanStatus.DRAFT,
        )
        plan_pri.learning_objectives.add(lo_pri)

        LessonPlanService.submit(plan_pri)

        # Primary Head Teacher (Teacher 3) approves -> Success
        LessonPlanService.approve(plan_pri, reviewed_by=self.teacher_3)
        plan_pri.refresh_from_db()
        self.assertEqual(plan_pri.status, LessonPlanStatus.APPROVED)
        self.assertEqual(plan_pri.reviewed_by, self.teacher_3)

    def test_school_without_leadership_allows_admin(self):
        """A school with 0 leadership assignments works seamlessly via Admin approval."""
        AcademicLeadershipAssignment.objects.all().delete()

        # Scheme of Work
        SchemeOfWorkService.submit(self.scheme_physics)
        SchemeOfWorkService.approve(self.scheme_physics, actor=self.admin_user)
        self.scheme_physics.refresh_from_db()
        self.assertEqual(self.scheme_physics.status, SchemeOfWorkStatus.APPROVED)

        # Lesson Plan
        LessonPlanService.submit(self.lesson_plan)
        LessonPlanService.approve(self.lesson_plan, reviewed_by=self.admin_user)
        self.lesson_plan.refresh_from_db()
        self.assertEqual(self.lesson_plan.status, LessonPlanStatus.APPROVED)

    def test_mandatory_actor_and_teacher_reviewer_hardening(self):
        """Verify actor is mandatory and review models store Teacher instances."""
        # 1. Scheme of Work actor=None raises ValidationError
        SchemeOfWorkService.submit(self.scheme_physics)
        with self.assertRaises(ValidationError):
            SchemeOfWorkService.approve(self.scheme_physics, actor=None)
        with self.assertRaises(ValidationError):
            SchemeOfWorkService.reject(self.scheme_physics, actor=None, reason="Rejection reason")

        # 2. Lesson Plan reviewed_by=None raises ValidationError
        LessonPlanService.submit(self.lesson_plan)
        with self.assertRaises(ValidationError):
            LessonPlanService.approve(self.lesson_plan, reviewed_by=None)
        with self.assertRaises(ValidationError):
            LessonPlanService.reject(self.lesson_plan, reviewed_by=None, reason="Rejection reason")

        # 3. Question Bank user=None raises ValidationError
        q = QuestionBankService.create_question(
            subject=self.subj_physics,
            grade_levels=[self.grade_jss1],
            question_type=QuestionType.MULTIPLE_CHOICE,
            text="What is acceleration?",
            created_by=self.teacher_2,
            options=[
                {"text": "Rate of change of velocity", "is_correct": True},
                {"text": "Rate of change of distance", "is_correct": False},
            ],
        )
        QuestionBankService.submit_for_review(q, user=self.teacher_2)
        with self.assertRaises(ValidationError):
            QuestionBankService.approve_question(q, user=None)
        with self.assertRaises(ValidationError):
            QuestionBankService.reject_question(q, user=None, comments="Rejection")

        # 4. CBT Exam actor=None raises ValidationError
        session = AssessmentSession.objects.create(
            assessment_type=AssessmentType.TEST,
            name="Hardening Test Session",
            academic_year=self.academic_year,
            term=self.term,
            start_date=timezone.now().date(),
            ends_date=timezone.now().date(),
            out_of=100,
        )
        grading_scheme = GradingScheme.objects.create(
            name="Hardening Scheme",
            academic_year=self.academic_year,
            grade_level=self.grade_jss1,
        )
        component = AssessmentComponent.objects.create(
            scheme=grading_scheme,
            name="Exam",
            max_score=100,
            weight=100,
            order=1,
        )
        exam = CBTExam.objects.create(
            session=session,
            component=component,
            subject=self.subj_physics,
            classroom=self.classroom_jss1,
            title="Physics Hardening Exam",
            duration_minutes=30,
            status=CBTExamStatus.READY,
            created_by=self.teacher_2,
        )
        ExamQuestion.objects.create(
            cbt_exam=exam,
            question_version=q.current_version,
            marks=10,
            order=1,
        )
        with self.assertRaises(ValidationError):
            CBTExamService.publish(exam=exam, actor=None)

        # 5. Verify QuestionReview.reviewed_by receives Teacher instance
        QuestionBankService.approve_question(q, user=self.admin_user)
        q.refresh_from_db()
        self.assertEqual(q.status, QuestionStatus.APPROVED)
        review = QuestionReview.objects.filter(question_version=q.current_version).first()
        self.assertIsNotNone(review)
        if review.reviewed_by:
            self.assertIsInstance(review.reviewed_by, Teacher)

        # 6. Verify SchemeOfWork.reviewed_by and LessonPlan.reviewed_by receive Teacher when reviewed by a Teacher
        AcademicLeadershipAssignment.objects.create(
            teacher=self.teacher_1,
            role=AcademicLeadershipRole.HOD,
            department=self.dept_science,
            academic_year=self.academic_year,
            is_active=True,
        )
        AcademicApprovalPolicyService.set_route(
            workflow=AcademicWorkflow.SCHEME_OF_WORK,
            approval_route=ApprovalRoute.ACADEMIC_LEADER_OR_ADMIN,
            actor=self.admin_user,
        )
        AcademicApprovalPolicyService.set_route(
            workflow=AcademicWorkflow.LESSON_PLAN,
            approval_route=ApprovalRoute.ACADEMIC_LEADER_OR_ADMIN,
            actor=self.admin_user,
        )

        SchemeOfWorkService.approve(self.scheme_physics, actor=self.teacher_1)
        self.scheme_physics.refresh_from_db()
        self.assertEqual(self.scheme_physics.reviewed_by, self.teacher_1)
        self.assertIsInstance(self.scheme_physics.reviewed_by, Teacher)

        LessonPlanService.approve(self.lesson_plan, reviewed_by=self.teacher_1)
        self.lesson_plan.refresh_from_db()
        self.assertEqual(self.lesson_plan.reviewed_by, self.teacher_1)
        self.assertIsInstance(self.lesson_plan.reviewed_by, Teacher)


