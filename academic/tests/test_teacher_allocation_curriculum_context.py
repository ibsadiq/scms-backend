from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from academic.models import (
    AllocatedSubject,
    ClassRoom,
    Curriculum,
    CurriculumAssignment,
    CurriculumSubject,
    GradeLevel,
    SectionType,
    StandardClassCode,
    Subject,
    Teacher,
)
from administration.models import AcademicYear, Term
from school.testcases import TenantTestCase
from tenants.models import TenantStatus


class TeacherAllocationCurriculumContextTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        super().setup_tenant(tenant)
        tenant.status = TenantStatus.ACTIVE

    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.teacher_user = User.objects.create_user(
            email="teacher1@test.com",
            password="password123",
            is_teacher=True,
        )
        self.other_teacher_user = User.objects.create_user(
            email="teacher2@test.com",
            password="password123",
            is_teacher=True,
        )
        self.admin_user = User.objects.create_user(
            email="admin@test.com",
            password="password123",
            is_admin=True,
        )

        self.teacher = Teacher.objects.create(
            user=self.teacher_user,
        )
        self.other_teacher = Teacher.objects.create(
            user=self.other_teacher_user,
        )

        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-07-31",
            active_year=True,
        )
        self.term = Term.objects.create(
            name="First Term",
            academic_year=self.year,
            start_date="2025-09-01",
            end_date="2025-12-15",
        )

        self.grade_jss1 = GradeLevel.objects.create(
            system_code=StandardClassCode.JSS_1,
            default_name="JSS 1",
            section=SectionType.JUNIOR_SECONDARY,
            sequence_order=10,
        )
        self.grade_jss2 = GradeLevel.objects.create(
            system_code=StandardClassCode.JSS_2,
            default_name="JSS 2",
            section=SectionType.JUNIOR_SECONDARY,
            sequence_order=11,
        )

        self.class_jss1a = ClassRoom.objects.create(
            name="JSS 1A",
            grade_level=self.grade_jss1,
            class_teacher=self.teacher,
        )
        self.class_jss2b = ClassRoom.objects.create(
            name="JSS 2B",
            grade_level=self.grade_jss2,
        )

        self.math = Subject.objects.create(name="Mathematics", subject_code="MTH")
        self.english = Subject.objects.create(name="English Language", subject_code="ENG")
        self.civic = Subject.objects.create(name="Civic Education", subject_code="CIV")

        self.curriculum_nerdc = Curriculum.objects.create(
            name="NERDC National Curriculum",
            version="2025",
            is_active=True,
        )
        self.curriculum_cambridge = Curriculum.objects.create(
            name="Cambridge Secondary 1",
            version="2025",
            is_active=True,
        )

        # 1. Exactly one mapping for Math + JSS 1 (MAPPED)
        self.nerdc_math = CurriculumSubject.objects.create(
            curriculum=self.curriculum_nerdc,
            grade_level=self.grade_jss1,
            name="Junior Secondary Mathematics",
            subject=self.math,
            is_active=True,
        )

        # 2. Ambiguous mappings for English + JSS 1 (AMBIGUOUS - NERDC + Cambridge)
        self.nerdc_eng = CurriculumSubject.objects.create(
            curriculum=self.curriculum_nerdc,
            grade_level=self.grade_jss1,
            name="English Studies",
            subject=self.english,
            is_active=True,
        )
        self.cambridge_eng = CurriculumSubject.objects.create(
            curriculum=self.curriculum_cambridge,
            grade_level=self.grade_jss1,
            name="Stage 7 English",
            subject=self.english,
            is_active=True,
        )

        # 3. Allocations for self.teacher
        self.alloc_math = AllocatedSubject.objects.create(
            teacher_name=self.teacher,
            subject=self.math,
            class_room=self.class_jss1a,
            academic_year=self.year,
            term=self.term,
            weekly_periods=4,
        )
        self.alloc_english = AllocatedSubject.objects.create(
            teacher_name=self.teacher,
            subject=self.english,
            class_room=self.class_jss1a,
            academic_year=self.year,
            term=self.term,
            weekly_periods=4,
        )
        self.alloc_civic_unmapped = AllocatedSubject.objects.create(
            teacher_name=self.teacher,
            subject=self.civic,
            class_room=self.class_jss2b,
            academic_year=self.year,
            term=self.term,
            weekly_periods=2,
        )

        # 4. Allocation for other teacher
        self.alloc_other = AllocatedSubject.objects.create(
            teacher_name=self.other_teacher,
            subject=self.math,
            class_room=self.class_jss2b,
            academic_year=self.year,
            term=self.term,
            weekly_periods=3,
        )

        self.teacher_client = APIClient(HTTP_HOST=self.domain.domain)
        self.teacher_client.force_authenticate(user=self.teacher_user)

        self.other_client = APIClient(HTTP_HOST=self.domain.domain)
        self.other_client.force_authenticate(user=self.other_teacher_user)

        self.admin_client = APIClient(HTTP_HOST=self.domain.domain)
        self.admin_client.force_authenticate(user=self.admin_user)

    def test_teacher_receives_only_own_teaching_allocations(self):
        url = "/api/academic/teachers/my-classes/"
        response = self.teacher_client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        assignments = data["teaching_assignments"]
        self.assertEqual(len(assignments), 3)

        alloc_ids = {a["allocation_id"] for a in assignments}
        self.assertIn(self.alloc_math.id, alloc_ids)
        self.assertIn(self.alloc_english.id, alloc_ids)
        self.assertIn(self.alloc_civic_unmapped.id, alloc_ids)
        self.assertNotIn(self.alloc_other.id, alloc_ids)

    def test_allocation_payload_contains_full_planning_identifiers(self):
        url = "/api/academic/teachers/my-classes/"
        response = self.teacher_client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        math_assignment = next(
            a for a in data["teaching_assignments"] if a["allocation_id"] == self.alloc_math.id
        )
        self.assertEqual(math_assignment["id"], self.alloc_math.id)
        self.assertEqual(math_assignment["allocation_id"], self.alloc_math.id)
        self.assertEqual(math_assignment["subject_id"], self.math.id)
        self.assertEqual(math_assignment["subject_name"], "Mathematics")
        self.assertEqual(math_assignment["classroom_id"], self.class_jss1a.id)
        self.assertEqual(math_assignment["classroom_name"], "JSS 1A")
        self.assertEqual(math_assignment["grade_level_id"], self.grade_jss1.id)
        self.assertEqual(math_assignment["grade_level_name"], "JSS 1")
        self.assertEqual(math_assignment["academic_year_id"], self.year.id)
        self.assertEqual(math_assignment["academic_year_name"], "2025/2026")
        self.assertEqual(math_assignment["term_id"], self.term.id)
        self.assertEqual(math_assignment["term_name"], "First Term")
        self.assertTrue(math_assignment["is_class_teacher"])

    def test_single_matching_curriculum_resolves_to_resolved_with_assignment(self):
        # In T1.5, deterministic resolution requires CurriculumAssignment
        CurriculumAssignment.objects.create(
            academic_year=self.year,
            curriculum=self.curriculum_nerdc,
            is_active=True,
        )
        url = "/api/academic/teachers/my-classes/"
        response = self.teacher_client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        math_assignment = next(
            a for a in data["teaching_assignments"] if a["allocation_id"] == self.alloc_math.id
        )
        context = math_assignment["curriculum_context"]
        self.assertEqual(context["status"], "RESOLVED")
        self.assertEqual(context["curriculum_subject_id"], self.nerdc_math.id)
        self.assertEqual(context["curriculum_subject_name"], "Junior Secondary Mathematics")
        self.assertEqual(context["curriculum_id"], self.curriculum_nerdc.id)
        self.assertEqual(context["curriculum_name"], "NERDC National Curriculum")

    def test_zero_matching_curriculum_resolves_to_subject_unmapped_with_assignment(self):
        # Civic education has no CurriculumSubject under NERDC
        CurriculumAssignment.objects.create(
            academic_year=self.year,
            curriculum=self.curriculum_nerdc,
            is_active=True,
        )
        url = "/api/academic/teachers/my-classes/"
        response = self.teacher_client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        civic_assignment = next(
            a for a in data["teaching_assignments"] if a["allocation_id"] == self.alloc_civic_unmapped.id
        )
        context = civic_assignment["curriculum_context"]
        self.assertEqual(context["status"], "SUBJECT_UNMAPPED")
        self.assertIsNone(context["curriculum_subject_id"])
        self.assertIsNone(context["curriculum_subject_name"])
        self.assertEqual(context["curriculum_id"], self.curriculum_nerdc.id)
        self.assertEqual(context["curriculum_name"], "NERDC National Curriculum")

    def test_no_assignment_resolves_to_no_curriculum_assigned(self):
        # Without CurriculumAssignment, status is NO_CURRICULUM_ASSIGNED
        url = "/api/academic/teachers/my-classes/"
        response = self.teacher_client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        eng_assignment = next(
            a for a in data["teaching_assignments"] if a["allocation_id"] == self.alloc_english.id
        )
        context = eng_assignment["curriculum_context"]
        self.assertEqual(context["status"], "NO_CURRICULUM_ASSIGNED")
        self.assertIsNone(context["curriculum_subject_id"])
        self.assertIsNone(context["curriculum_subject_name"])
        self.assertIsNone(context["curriculum_id"])
        self.assertIsNone(context["curriculum_name"])

    def test_admin_access_on_my_classes_remains_backward_compatible(self):
        url = "/api/academic/teachers/my-classes/"
        response = self.admin_client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("homeroom_classes", data)
        self.assertIn("teaching_assignments", data)
        # Admin without teacher profile gets active classrooms as homeroom_classes
        self.assertEqual(len(data["homeroom_classes"]), 2)
