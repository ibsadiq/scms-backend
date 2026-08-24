from django.urls import reverse
from school.testcases import TenantTestCase
from rest_framework.test import APIClient
from academic.models import LessonPlan, LessonPlanStatus, Teacher, Subject, Curriculum, CurriculumSubject, GradeLevel, SchoolSection, Term, ClassLevel, ClassRoom, AllocatedSubject, SchemeOfWork, SchemeOfWorkItem, CurriculumTopic, Topic, SchemeOfWorkStatus
from administration.models import AcademicYear
from users.models import CustomUser
from tenants.models import TenantStatus

class LessonPlanLifecycleTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.name = "Lesson Plan Workflow School"
        tenant.status = TenantStatus.ACTIVE

    @classmethod
    def setup_domain(cls, domain):
        domain.is_primary = True
        return domain

    def setUp(self):
        self.admin = CustomUser.objects.create_user(email="admin@workflow.test", password="x", is_admin=True)
        self.teacher_user = CustomUser.objects.create_user(email="teacher@workflow.test", password="x", is_teacher=True)
        self.teacher = Teacher.objects.create(user=self.teacher_user)

        self.section = SchoolSection.objects.create(system_code="SENIOR_SECONDARY", default_name="Secondary", sequence_order=4)
        self.grade = GradeLevel.objects.create(system_code="SS_1", default_name="SS 1", section="SSS", sequence_order=14)
        self.classlevel = ClassLevel.objects.create(name="SS 1A", grade_level=self.grade)
        self.classroom = ClassRoom.objects.create(name=self.classlevel)
        self.year = AcademicYear.objects.create(name="2023/2024", start_date="2023-09-01", end_date="2024-07-31", active_year=True)
        self.term = Term.objects.create(name="First Term", academic_year=self.year, start_date="2023-09-01", end_date="2023-12-15")
        self.subject = Subject.objects.create(name="Mathematics")
        self.curriculum = Curriculum.objects.create(name="Standard")
        self.curriculum_subject = CurriculumSubject.objects.create(
            curriculum=self.curriculum,
            subject=self.subject,
            grade_level=self.grade
        )

        self.allocation = AllocatedSubject.objects.create(
            teacher_name=self.teacher,
            subject=self.subject,
            class_room=self.classroom,
            academic_year=self.year,
            weekly_periods=2
        )

        self.scheme = SchemeOfWork.objects.create(
            academic_year=self.year,
            term=self.term,
            curriculum_subject=self.curriculum_subject,
            status=SchemeOfWorkStatus.APPROVED,
            created_by=self.teacher
        )
        self.topic = Topic.objects.create(name="Algebra", subject=self.subject, grade_level=self.grade)
        self.curriculum_topic = CurriculumTopic.objects.create(
            curriculum_subject=self.curriculum_subject,
            topic=self.topic
        )
        self.scheme_item = SchemeOfWorkItem.objects.create(
            scheme=self.scheme,
            curriculum_topic=self.curriculum_topic,
            week_number=1
        )

        self.plan = LessonPlan.objects.create(
            scheme_item=self.scheme_item,
            allocation=self.allocation,
            lesson_date="2024-01-01",
            title="Algebra basics",
            status=LessonPlanStatus.DRAFT,
        )

        self.client = APIClient(HTTP_HOST=self.domain.domain)
        self.client.force_authenticate(self.admin)
        self.teacher_client = APIClient(HTTP_HOST=self.domain.domain)
        self.teacher_client.force_authenticate(self.teacher_user)

    def post_action(self, plan, action, data=None, client=None):
        if client is None:
            client = self.client
        return client.post(
            reverse(f"lesson-plan-{action}", args=[plan.pk]),
            data or {}, format="json",
        )

    def test_valid_transitions(self):
        resp = self.post_action(self.plan, "submit", client=self.teacher_client)
        self.assertEqual(resp.status_code, 200)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, LessonPlanStatus.SUBMITTED)

        resp = self.post_action(self.plan, "approve")
        self.assertEqual(resp.status_code, 200)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, LessonPlanStatus.APPROVED)

    def test_valid_rejection_and_reopen(self):
        self.post_action(self.plan, "submit", client=self.teacher_client)
        
        resp = self.post_action(self.plan, "reject", {"reason": "Not enough activities"})
        self.assertEqual(resp.status_code, 200)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, LessonPlanStatus.REJECTED)

        resp = self.post_action(self.plan, "reopen-for-revision")
        self.assertEqual(resp.status_code, 200)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, LessonPlanStatus.DRAFT)

    def test_invalid_transitions_are_rejected(self):
        resp = self.post_action(self.plan, "approve")
        self.assertEqual(resp.status_code, 400)

    def test_status_cannot_be_changed_through_patch(self):
        resp = self.client.patch(
            reverse("lesson-plan-detail", args=[self.plan.pk]),
            {"status": LessonPlanStatus.APPROVED}, format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, LessonPlanStatus.DRAFT)
