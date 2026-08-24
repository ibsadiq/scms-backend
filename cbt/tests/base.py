from school.testcases import TenantTestCase as TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from academic.models import (
    Department,
    Subject,
    Teacher,
    GradeLevel,
    ClassLevel,
    ClassRoom,
    Curriculum,
    CurriculumSubject,
    Topic,
    SubTopic,
    CurriculumTopic,
    LearningObjective,
    AllocatedSubject,
    SectionType,
    AcademicLeadershipRole,
    AcademicLeadershipAssignment,
    AcademicWorkflow,
    ApprovalRoute,
    AcademicApprovalPolicy,
    Student,
    StudentClassEnrollment,
)
from administration.models import AcademicYear, Term
from examination.models import (
    GradingScheme,
    AssessmentComponent,
    AssessmentSession,
    AssessmentType,
)
from academic.services import AcademicApprovalPolicyService, AcademicLeadershipService

User = get_user_model()


class TenantAPIClient(APIClient):
    def __init__(self, tenant, enforce_csrf_checks=False, **defaults):
        super().__init__(enforce_csrf_checks=enforce_csrf_checks, **defaults)
        self.tenant = tenant

    def _base_environ(self, **request):
        environ = super()._base_environ(**request)
        if hasattr(self.tenant, "domains") and self.tenant.domains.exists():
            domain = self.tenant.domains.first().domain
        elif hasattr(self.tenant, "domain_url"):
            domain = self.tenant.domain_url
        else:
            domain = "test.test.com"
        environ["HTTP_HOST"] = domain
        return environ


class CBTAPITestBase(TestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.status = "active"
        return super().setup_tenant(tenant)

    def setUp(self):
        super().setUp()
        self.client = TenantAPIClient(self.tenant)

        # Users
        self.admin_user = User.objects.create_user(
            email="admin@cbt.com",
            password="password123",
            first_name="Admin",
            last_name="User",
            is_admin=True,
            is_staff=True,
            is_superuser=True,
        )
        self.teacher_user_1 = User.objects.create_user(
            email="teacher1@cbt.com",
            password="password123",
            first_name="Alice",
            last_name="Teacher",
            is_teacher=True,
        )
        self.teacher_user_2 = User.objects.create_user(
            email="teacher2@cbt.com",
            password="password123",
            first_name="Bob",
            last_name="Teacher",
            is_teacher=True,
        )
        self.student_user = User.objects.create_user(
            email="student@cbt.com",
            password="password123",
            first_name="Sam",
            last_name="Student",
            is_student=True,
        )
        self.other_student_user = User.objects.create_user(
            email="otherstudent@cbt.com",
            password="password123",
            first_name="Oscar",
            last_name="Student",
            is_student=True,
        )

        # Teachers
        self.teacher_1 = Teacher.objects.create(user=self.teacher_user_1)
        self.teacher_2 = Teacher.objects.create(user=self.teacher_user_2)

        # Academic Structure
        self.dept_science = Department.objects.create(name="Science")
        self.subj_math = Subject.objects.create(
            name="Mathematics",
            subject_code="MATH101",
            department=self.dept_science,
        )
        self.subj_physics = Subject.objects.create(
            name="Physics",
            subject_code="PHY101",
            department=self.dept_science,
        )

        self.academic_year = AcademicYear.objects.create(
            name="2026/2027",
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timezone.timedelta(days=365),
            active_year=True,
        )
        self.term = Term.objects.create(
            name="First Term",
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timezone.timedelta(days=90),
            academic_year=self.academic_year,
        )

        self.grade_jss1 = GradeLevel.objects.create(
            system_code="JSS_1",
            default_name="JSS 1",
            section=SectionType.JUNIOR_SECONDARY,
            sequence_order=11,
        )
        self.class_level_jss1 = ClassLevel.objects.create(
            name="JSS 1",
            grade_level=self.grade_jss1,
        )
        self.classroom_jss1 = ClassRoom.objects.create(
            name=self.class_level_jss1,
        )
        self.classroom_jss2 = ClassRoom.objects.create(
            name=self.class_level_jss1,
        )

        # Students & Enrollments
        self.student = Student.objects.create(
            user=self.student_user,
            student_id="STU-001",
            admission_number="ADM-001",
            first_name="Sam",
            last_name="Student",
            parent_contact="08012345678",
            classroom=self.classroom_jss1,
            class_level=self.class_level_jss1,
        )
        self.enrollment = StudentClassEnrollment.objects.create(
            student=self.student,
            classroom=self.classroom_jss1,
            academic_year=self.academic_year,
            is_active=True,
        )

        self.other_student = Student.objects.create(
            user=self.other_student_user,
            student_id="STU-002",
            admission_number="ADM-002",
            first_name="Oscar",
            last_name="Student",
            parent_contact="08087654321",
            classroom=self.classroom_jss2,
            class_level=self.class_level_jss1,
        )
        self.other_enrollment = StudentClassEnrollment.objects.create(
            student=self.other_student,
            classroom=self.classroom_jss2,
            academic_year=self.academic_year,
            is_active=True,
        )

        # Teacher Allocation: Teacher 1 teaches Math in JSS1
        self.alloc_math = AllocatedSubject.objects.create(
            teacher_name=self.teacher_1,
            subject=self.subj_math,
            class_room=self.classroom_jss1,
            academic_year=self.academic_year,
            term=self.term,
            weekly_periods=4,
        )

        # Curriculum & Topics
        self.curriculum = Curriculum.objects.create(name="National Curriculum")
        self.curr_sub_math = CurriculumSubject.objects.create(
            curriculum=self.curriculum,
            grade_level=self.grade_jss1,
            subject=self.subj_math,
        )
        self.topic_algebra = Topic.objects.create(
            subject=self.subj_math,
            grade_level=self.grade_jss1,
            name="Algebra",
        )
        self.curr_topic_algebra = CurriculumTopic.objects.create(
            curriculum_subject=self.curr_sub_math,
            topic=self.topic_algebra,
            order=1,
        )
        self.lo_algebra = LearningObjective.objects.create(
            curriculum_topic=self.curr_topic_algebra,
            description="Solve linear equations",
            order=1,
        )

        # Examination Framework
        self.session = AssessmentSession.objects.create(
            assessment_type=AssessmentType.EXAMINATION,
            name="First Term Exams",
            academic_year=self.academic_year,
            term=self.term,
            start_date=timezone.now().date(),
            ends_date=timezone.now().date() + timezone.timedelta(days=14),
            out_of=100,
        )
        self.grading_scheme = GradingScheme.objects.create(
            name="Default Scheme",
            academic_year=self.academic_year,
            grade_level=self.grade_jss1,
        )
        self.component = AssessmentComponent.objects.create(
            scheme=self.grading_scheme,
            name="CBT Assessment",
            max_score=100,
            weight=100,
            order=1,
        )
