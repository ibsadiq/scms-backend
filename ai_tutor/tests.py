from school.testcases import TenantTestCase as TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied

from academic.models import (
    GradeLevel,
    Subject,
    Teacher,
    Student,
    ClassLevel,
    ClassRoom,
    AllocatedSubject,
    StudentClassEnrollment,
    Curriculum,
    CurriculumSubject,
    CurriculumTopic,
    LearningObjective,
    Topic,
    SubTopic,
    SchemeOfWork,
    SchemeOfWorkItem,
    LessonPlan,
    LessonDelivery,
    LessonPlanMaterial,
)
from administration.models import AcademicYear, Term
from ai_tutor.models import (
    TeacherAvatarSetting,
    TutorSession,
    TutorMessage,
    TutorSessionInsight,
)
from ai_tutor.services import (
    TutorSessionService,
    TutorContextService,
    TutorMaterialService,
    TutorResponseService,
    TutorInsightService,
    BaseTutorLLMProvider,
    TutorLLMService,
)

User = get_user_model()


class MockLLMProvider(BaseTutorLLMProvider):
    def generate_reply_stream(self, *, system_instruction: str, conversation_history, model=None):
        yield "Hello "
        yield "from "
        yield "Mock LLM!"

    def generate_reply_sync(self, *, system_instruction: str, conversation_history, model=None):
        return "Hello from Mock LLM!"


class AITutorDomainTests(TestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        return super().setup_tenant(tenant)

    def setUp(self):
        TutorLLMService.set_provider(MockLLMProvider())

        # 1. Users
        self.teacher_user = User.objects.create_user(
            email="teacher@school.com",
            password="password123",
            first_name="Jane",
            last_name="Doe",
        )
        self.student_user = User.objects.create_user(
            email="student@school.com",
            password="password123",
            first_name="Alex",
            last_name="Smith",
        )
        self.other_student_user = User.objects.create_user(
            email="other@school.com",
            password="password123",
            first_name="Bob",
            last_name="Jones",
        )

        # 2. Academic structure
        self.teacher = Teacher.objects.create(user=self.teacher_user)
        self.student = Student.objects.create(
            user=self.student_user,
            first_name="Alex",
            last_name="Smith",
            admission_number="ADM-001",
            parent_contact="+2348012345678",
        )
        self.other_student = Student.objects.create(
            user=self.other_student_user,
            first_name="Bob",
            last_name="Jones",
            admission_number="ADM-002",
            parent_contact="+2348012345679",
        )

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
        self.grade_level = GradeLevel.objects.create(
            system_code="JSS_1",
            default_name="JSS 1",
            section="JSS",
            sequence_order=1,
        )
        self.class_level = ClassLevel.objects.create(
            name="JSS 1A",
            grade_level=self.grade_level,
        )
        self.classroom = ClassRoom.objects.create(name=self.class_level)

        self.enrollment = StudentClassEnrollment.objects.create(
            student=self.student,
            classroom=self.classroom,
            academic_year=self.academic_year,
            is_active=True,
        )

        self.subject = Subject.objects.create(name="Mathematics", subject_code="MTH")
        self.other_subject = Subject.objects.create(name="Physics", subject_code="PHY")

        # Teacher allocation
        self.allocation = AllocatedSubject.objects.create(
            teacher_name=self.teacher,
            subject=self.subject,
            class_room=self.classroom,
            academic_year=self.academic_year,
            term=self.term,
            weekly_periods=4,
        )

        # Avatar setting
        self.avatar_setting = TeacherAvatarSetting.objects.create(
            teacher=self.teacher,
            avatar_style=TeacherAvatarSetting.AvatarStyle.PHOTO_ANIMATED,
            teaching_tone=TeacherAvatarSetting.TeachingTone.SOCRATIC,
            custom_system_instructions="Encourage algebraic thinking.",
            is_ai_tutor_enabled=True,
            allow_direct_answers=False,
        )

        # Curriculum
        self.curriculum = Curriculum.objects.create(name="National Curriculum")
        self.curr_sub = CurriculumSubject.objects.create(
            curriculum=self.curriculum,
            grade_level=self.class_level.grade_level,
            subject=self.subject,
        )
        self.topic = Topic.objects.create(
            subject=self.subject,
            grade_level=self.grade_level,
            name="Algebraic Expressions",
        )
        self.curr_topic = CurriculumTopic.objects.create(
            curriculum_subject=self.curr_sub,
            topic=self.topic,
            order=1,
        )
        self.lo1 = LearningObjective.objects.create(
            curriculum_topic=self.curr_topic,
            description="Identify variables and constants",
            order=1,
        )
        self.lo2 = LearningObjective.objects.create(
            curriculum_topic=self.curr_topic,
            description="Simplify linear expressions",
            order=2,
        )

        # Scheme of Work & Lesson Plan
        self.scheme = SchemeOfWork.objects.create(
            curriculum_subject=self.curr_sub,
            academic_year=self.academic_year,
            term=self.term,
        )
        self.scheme_item = SchemeOfWorkItem.objects.create(
            scheme=self.scheme,
            week_number=1,
            curriculum_topic=self.curr_topic,
        )
        self.lesson_plan = LessonPlan.objects.create(
            scheme_item=self.scheme_item,
            allocation=self.allocation,
            lesson_date="2026-09-10",
            title="Introduction to Algebra",
            lesson_content="Algebra involves using symbols to represent numbers.",
        )
        self.lesson_plan.learning_objectives.set([self.lo1, self.lo2])

        # Lesson Delivery
        self.delivery = LessonDelivery.objects.create(
            lesson_plan=self.lesson_plan,
            teacher_notes="Students understood variables well.",
            learner_response="Active engagement.",
        )
        self.delivery.objectives_covered.set([self.lo1])  # Only lo1 delivered

    def test_start_session_resolves_allocated_teacher(self):
        session = TutorSessionService.start_or_get_session(
            student=self.student,
            subject=self.subject,
            lesson_plan=self.lesson_plan,
            lesson_delivery=self.delivery,
            curriculum_topic=self.curr_topic,
        )
        self.assertEqual(session.teacher, self.teacher)
        self.assertEqual(session.student, self.student)
        self.assertEqual(session.subject, self.subject)
        self.assertEqual(session.lesson_plan, self.lesson_plan)

    def test_start_session_fails_if_no_teacher_allocated(self):
        with self.assertRaises(ValidationError) as ctx:
            TutorSessionService.start_or_get_session(
                student=self.student,
                subject=self.other_subject,  # No teacher allocated for physics
            )
        self.assertIn("No teacher is assigned to teach", str(ctx.exception))

    def test_start_session_fails_if_ai_tutor_disabled(self):
        self.avatar_setting.is_ai_tutor_enabled = False
        self.avatar_setting.save()

        with self.assertRaises(ValidationError) as ctx:
            TutorSessionService.start_or_get_session(
                student=self.student,
                subject=self.subject,
            )
        self.assertIn("AI Tutor is currently disabled", str(ctx.exception))

    def test_context_prioritizes_delivered_objectives(self):
        session = TutorSessionService.start_or_get_session(
            student=self.student,
            subject=self.subject,
            lesson_plan=self.lesson_plan,
            lesson_delivery=self.delivery,
            curriculum_topic=self.curr_topic,
        )
        ctx = TutorContextService.assemble_structured_context(session)
        
        # lo1 was covered in delivery, lo2 was planned but not delivered
        self.assertIn("Identify variables and constants", ctx["curriculum"]["delivered_objectives"])
        self.assertIn("Simplify linear expressions", ctx["curriculum"]["planned_undelivered_objectives"])

        prompt = TutorContextService.build_system_instruction(session)
        self.assertIn("ACTUALLY TAUGHT IN CLASS", prompt)
        self.assertIn("Identify variables and constants", prompt)
        self.assertIn("PLANNED / UPCOMING CONCEPTS", prompt)
        self.assertIn("Simplify linear expressions", prompt)

    def test_send_message_sync_and_insight_generation(self):
        session = TutorSessionService.start_or_get_session(
            student=self.student,
            subject=self.subject,
            lesson_plan=self.lesson_plan,
            lesson_delivery=self.delivery,
            curriculum_topic=self.curr_topic,
        )

        msg = TutorResponseService.send_message_sync(
            session=session,
            user=self.student_user,
            message_text="Can you explain what a variable is again?",
        )

        self.assertEqual(msg.role, TutorMessage.Role.ASSISTANT)
        self.assertEqual(msg.content, "Hello from Mock LLM!")

        # Verify insight created
        insight = TutorSessionInsight.objects.get(session=session)
        self.assertIsNotNone(insight)
        self.assertIn("Student engaged in 1 inquiry turn", insight.summary)

    def test_unauthorized_user_cannot_send_message(self):
        session = TutorSessionService.start_or_get_session(
            student=self.student,
            subject=self.subject,
            lesson_plan=self.lesson_plan,
        )

        with self.assertRaises(PermissionDenied):
            TutorResponseService.send_message_sync(
                session=session,
                user=self.other_student_user,  # Bob trying to message Alex's session
                message_text="Hello",
            )
