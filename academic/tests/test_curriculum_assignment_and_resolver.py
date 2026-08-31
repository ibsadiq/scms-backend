from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from rest_framework import status
from rest_framework.test import APIClient

from academic.models import (
    AllocatedSubject,
    ClassRoom,
    Curriculum,
    CurriculumAssignment,
    CurriculumSubject,
    CurriculumTopic,
    GradeLevel,
    PublishedScheme,
    PublishedSchemeEntry,
    PublishedSchemeEntryType,
    SchemeOfWork,
    SchemeOfWorkStatus,
    SectionType,
    StandardClassCode,
    Subject,
    Teacher,
    Topic,
    SchoolSection,
)
from academic.services import (
    CurriculumAssignmentResolver,
    PublishedSchemeAdoptionService,
)
from administration.models import AcademicYear, Term
from school.testcases import TenantTestCase
from tenants.models import TenantStatus


class CurriculumAssignmentAndResolverTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        super().setup_tenant(tenant)
        tenant.status = TenantStatus.ACTIVE

    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.admin_user = User.objects.create_user(
            email="admin@school.test",
            password="password123",
            is_admin=True,
        )
        self.teacher_user = User.objects.create_user(
            email="teacher@school.test",
            password="password123",
            is_teacher=True,
        )
        self.other_teacher_user = User.objects.create_user(
            email="other@school.test",
            password="password123",
            is_teacher=True,
        )

        self.teacher = Teacher.objects.create(user=self.teacher_user)
        self.other_teacher = Teacher.objects.create(user=self.other_teacher_user)

        self.year_2025 = AcademicYear.objects.create(
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-07-31",
            active_year=True,
        )
        self.year_2026 = AcademicYear.objects.create(
            name="2026/2027",
            start_date="2026-09-01",
            end_date="2027-07-31",
            active_year=False,
        )
        self.term_1 = Term.objects.create(
            name="First Term",
            academic_year=self.year_2025,
            start_date="2025-09-01",
            end_date="2025-12-15",
        )

        # School sections
        self.sec_primary = SchoolSection.objects.create(
            system_code=SectionType.PRIMARY,
            default_name="Primary",
            sequence_order=1,
        )
        self.sec_jss = SchoolSection.objects.create(
            system_code=SectionType.JUNIOR_SECONDARY,
            default_name="Junior Secondary",
            sequence_order=2,
        )

        # Grade levels
        self.grade_basic1 = GradeLevel.objects.create(
            system_code=StandardClassCode.BASIC_1,
            default_name="Basic 1",
            section=SectionType.PRIMARY,
            sequence_order=1,
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

        # Classrooms
        self.class_jss1a = ClassRoom.objects.create(name="JSS 1A", grade_level=self.grade_jss1)
        self.class_jss1b = ClassRoom.objects.create(name="JSS 1B", grade_level=self.grade_jss1)
        self.class_jss2a = ClassRoom.objects.create(name="JSS 2A", grade_level=self.grade_jss2)

        # Subjects
        self.math = Subject.objects.create(name="Mathematics", subject_code="MTH")
        self.english = Subject.objects.create(name="English Language", subject_code="ENG")
        self.civic = Subject.objects.create(name="Civic Education", subject_code="CIV")

        # Curricula
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

        # Canonical CurriculumSubjects
        self.nerdc_jss1_math = CurriculumSubject.objects.create(
            curriculum=self.curriculum_nerdc,
            grade_level=self.grade_jss1,
            name="NERDC JSS1 Mathematics",
            subject=self.math,
            is_active=True,
        )
        self.cambridge_jss1_math = CurriculumSubject.objects.create(
            curriculum=self.curriculum_cambridge,
            grade_level=self.grade_jss1,
            name="Cambridge Stage 7 Math",
            subject=self.math,
            is_active=True,
        )
        self.topic_algebra = Topic.objects.create(
            name="Algebra",
            subject=self.math,
            grade_level=self.grade_jss1,
        )
        self.nerdc_topic_algebra = CurriculumTopic.objects.create(
            curriculum_subject=self.nerdc_jss1_math,
            topic=self.topic_algebra,
        )
        self.cambridge_topic_algebra = CurriculumTopic.objects.create(
            curriculum_subject=self.cambridge_jss1_math,
            topic=self.topic_algebra,
        )

        # Teacher allocations
        self.alloc_jss1a_math = AllocatedSubject.objects.create(
            teacher_name=self.teacher,
            subject=self.math,
            class_room=self.class_jss1a,
            academic_year=self.year_2025,
            term=self.term_1,
            weekly_periods=4,
        )
        self.alloc_jss1b_math = AllocatedSubject.objects.create(
            teacher_name=self.teacher,
            subject=self.math,
            class_room=self.class_jss1b,
            academic_year=self.year_2025,
            term=self.term_1,
            weekly_periods=4,
        )
        self.alloc_jss2a_civic = AllocatedSubject.objects.create(
            teacher_name=self.teacher,
            subject=self.civic,
            class_room=self.class_jss2a,
            academic_year=self.year_2025,
            term=self.term_1,
            weekly_periods=2,
        )

        self.admin_client = APIClient(HTTP_HOST=self.domain.domain)
        self.admin_client.force_authenticate(user=self.admin_user)

        self.teacher_client = APIClient(HTTP_HOST=self.domain.domain)
        self.teacher_client.force_authenticate(user=self.teacher_user)

    # 1. Model & Validation Constraints
    def test_single_scope_constraint_rejects_multiple_scope_pointers(self):
        assign = CurriculumAssignment(
            academic_year=self.year_2025,
            curriculum=self.curriculum_nerdc,
            section=self.sec_jss,
            grade_level=self.grade_jss1,
        )
        with self.assertRaises(ValidationError):
            assign.clean()

    def test_duplicate_active_school_wide_assignment_rejected(self):
        CurriculumAssignment.objects.create(
            academic_year=self.year_2025,
            curriculum=self.curriculum_nerdc,
            is_active=True,
        )
        with self.assertRaises(IntegrityError):
            CurriculumAssignment.objects.create(
                academic_year=self.year_2025,
                curriculum=self.curriculum_cambridge,
                is_active=True,
            )

    def test_duplicate_active_section_assignment_rejected(self):
        CurriculumAssignment.objects.create(
            academic_year=self.year_2025,
            curriculum=self.curriculum_nerdc,
            section=self.sec_jss,
            is_active=True,
        )
        with self.assertRaises(IntegrityError):
            CurriculumAssignment.objects.create(
                academic_year=self.year_2025,
                curriculum=self.curriculum_cambridge,
                section=self.sec_jss,
                is_active=True,
            )

    def test_inactive_historical_assignments_can_coexist(self):
        first = CurriculumAssignment.objects.create(
            academic_year=self.year_2025,
            curriculum=self.curriculum_nerdc,
            section=self.sec_jss,
            is_active=False,
        )
        second = CurriculumAssignment.objects.create(
            academic_year=self.year_2025,
            curriculum=self.curriculum_cambridge,
            section=self.sec_jss,
            is_active=True,
        )
        self.assertEqual(CurriculumAssignment.objects.filter(academic_year=self.year_2025, section=self.sec_jss).count(), 2)

    # 2. Specificity & Precedence Resolution Tests
    def test_resolver_returns_no_curriculum_assigned_when_no_assignments_exist(self):
        result = CurriculumAssignmentResolver.resolve_for_allocation(self.alloc_jss1a_math)
        self.assertEqual(result["status"], "NO_CURRICULUM_ASSIGNED")
        self.assertIsNone(result["curriculum_id"])
        self.assertIsNone(result["curriculum_subject_id"])

    def test_school_wide_fallback_resolution(self):
        CurriculumAssignment.objects.create(
            academic_year=self.year_2025,
            curriculum=self.curriculum_nerdc,
            is_active=True,
        )
        result = CurriculumAssignmentResolver.resolve_for_allocation(self.alloc_jss1a_math)
        self.assertEqual(result["status"], "RESOLVED")
        self.assertEqual(result["curriculum_id"], self.curriculum_nerdc.id)
        self.assertEqual(result["curriculum_subject_id"], self.nerdc_jss1_math.id)
        self.assertEqual(result["assignment_scope"], "SCHOOL")

    def test_section_overrides_school_wide(self):
        CurriculumAssignment.objects.create(
            academic_year=self.year_2025,
            curriculum=self.curriculum_nerdc,
            is_active=True,
        )
        CurriculumAssignment.objects.create(
            academic_year=self.year_2025,
            curriculum=self.curriculum_cambridge,
            section=self.sec_jss,
            is_active=True,
        )
        result = CurriculumAssignmentResolver.resolve_for_allocation(self.alloc_jss1a_math)
        self.assertEqual(result["status"], "RESOLVED")
        self.assertEqual(result["curriculum_id"], self.curriculum_cambridge.id)
        self.assertEqual(result["curriculum_subject_id"], self.cambridge_jss1_math.id)
        self.assertEqual(result["assignment_scope"], "SECTION")

    def test_grade_overrides_section(self):
        CurriculumAssignment.objects.create(
            academic_year=self.year_2025,
            curriculum=self.curriculum_nerdc,
            section=self.sec_jss,
            is_active=True,
        )
        CurriculumAssignment.objects.create(
            academic_year=self.year_2025,
            curriculum=self.curriculum_cambridge,
            grade_level=self.grade_jss1,
            is_active=True,
        )
        result = CurriculumAssignmentResolver.resolve_for_allocation(self.alloc_jss1a_math)
        self.assertEqual(result["status"], "RESOLVED")
        self.assertEqual(result["curriculum_id"], self.curriculum_cambridge.id)
        self.assertEqual(result["curriculum_subject_id"], self.cambridge_jss1_math.id)
        self.assertEqual(result["assignment_scope"], "GRADE_LEVEL")

    def test_classroom_overrides_grade(self):
        CurriculumAssignment.objects.create(
            academic_year=self.year_2025,
            curriculum=self.curriculum_cambridge,
            grade_level=self.grade_jss1,
            is_active=True,
        )
        # JSS 1B gets NERDC override
        CurriculumAssignment.objects.create(
            academic_year=self.year_2025,
            curriculum=self.curriculum_nerdc,
            classroom=self.class_jss1b,
            is_active=True,
        )
        res_a = CurriculumAssignmentResolver.resolve_for_allocation(self.alloc_jss1a_math)
        res_b = CurriculumAssignmentResolver.resolve_for_allocation(self.alloc_jss1b_math)

        self.assertEqual(res_a["curriculum_id"], self.curriculum_cambridge.id)
        self.assertEqual(res_a["curriculum_subject_id"], self.cambridge_jss1_math.id)

        self.assertEqual(res_b["curriculum_id"], self.curriculum_nerdc.id)
        self.assertEqual(res_b["curriculum_subject_id"], self.nerdc_jss1_math.id)
        self.assertEqual(res_b["assignment_scope"], "CLASSROOM")

    def test_subject_unmapped_status_when_curriculum_assigned_but_subject_has_no_mapping(self):
        CurriculumAssignment.objects.create(
            academic_year=self.year_2025,
            curriculum=self.curriculum_nerdc,
            grade_level=self.grade_jss2,
            is_active=True,
        )
        # civic in JSS 2 has no CurriculumSubject mapping
        result = CurriculumAssignmentResolver.resolve_for_allocation(self.alloc_jss2a_civic)
        self.assertEqual(result["status"], "SUBJECT_UNMAPPED")
        self.assertEqual(result["curriculum_id"], self.curriculum_nerdc.id)
        self.assertIsNone(result["curriculum_subject_id"])

    # 3. Teacher My Classes API Tests
    def test_teacher_my_classes_returns_deterministic_curriculum_context(self):
        CurriculumAssignment.objects.create(
            academic_year=self.year_2025,
            curriculum=self.curriculum_nerdc,
            is_active=True,
        )
        response = self.teacher_client.get("/api/academic/teachers/my-classes/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        jss1a = next(a for a in data["teaching_assignments"] if a["allocation_id"] == self.alloc_jss1a_math.id)
        self.assertEqual(jss1a["curriculum_context"]["status"], "RESOLVED")
        self.assertEqual(jss1a["curriculum_context"]["curriculum_name"], "NERDC National Curriculum")
        self.assertEqual(jss1a["curriculum_context"]["curriculum_subject_name"], "NERDC JSS1 Mathematics")

    # 4. CurriculumAssignment Admin API & Permissions
    def test_admin_can_create_and_manage_curriculum_assignments(self):
        post_data = {
            "academic_year": self.year_2025.id,
            "curriculum": self.curriculum_nerdc.id,
            "section": self.sec_jss.id,
            "notes": "JSS NERDC assignment",
        }
        res = self.admin_client.post("/api/academic/curriculum-assignments/", post_data, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.json() if hasattr(res, 'json') else res.content)
        self.assertEqual(res.json()["created_by_name"], str(self.admin_user))

    def test_teacher_cannot_create_curriculum_assignments(self):
        post_data = {
            "academic_year": self.year_2025.id,
            "curriculum": self.curriculum_nerdc.id,
        }
        res = self.teacher_client.post("/api/academic/curriculum-assignments/", post_data, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    # 5. Published Scheme Adoption Enforcement
    def test_teacher_can_adopt_published_scheme_matching_assigned_curriculum(self):
        CurriculumAssignment.objects.create(
            academic_year=self.year_2025,
            curriculum=self.curriculum_nerdc,
            is_active=True,
        )
        published = PublishedScheme.objects.create(
            curriculum_subject=self.nerdc_jss1_math,
            name="NERDC Math Scheme",
            version="2025",
            is_active=True,
        )
        PublishedSchemeEntry.objects.create(
            published_scheme=published,
            term_number=1,
            week_start=1,
            curriculum_topic=self.nerdc_topic_algebra,
            title="Algebra intro",
            order=1,
        )
        payload = {
            "published_scheme": published.id,
            "academic_year": self.year_2025.id,
            "term": self.term_1.id,
        }
        capability = self.teacher_client.get("/api/academic/schemes-of-work/adoption-capability/", payload)
        self.assertTrue(capability.json()["allowed"])

        adopt_res = self.teacher_client.post("/api/academic/schemes-of-work/adopt-published/", payload, format="json")
        self.assertEqual(adopt_res.status_code, status.HTTP_201_CREATED, adopt_res.json() if hasattr(adopt_res, 'json') else adopt_res.content)

    def test_teacher_cannot_adopt_published_scheme_from_unassigned_curriculum(self):
        # School is assigned NERDC for JSS 1
        CurriculumAssignment.objects.create(
            academic_year=self.year_2025,
            curriculum=self.curriculum_nerdc,
            is_active=True,
        )
        # Cambridge published scheme for same Mathematics + JSS 1
        cambridge_scheme = PublishedScheme.objects.create(
            curriculum_subject=self.cambridge_jss1_math,
            name="Cambridge Math Scheme",
            version="2025",
            is_active=True,
        )
        PublishedSchemeEntry.objects.create(
            published_scheme=cambridge_scheme,
            term_number=1,
            week_start=1,
            curriculum_topic=self.cambridge_topic_algebra,
            title="Cambridge Algebra",
            order=1,
        )
        payload = {
            "published_scheme": cambridge_scheme.id,
            "academic_year": self.year_2025.id,
            "term": self.term_1.id,
        }
        capability = self.teacher_client.get("/api/academic/schemes-of-work/adoption-capability/", payload)
        self.assertFalse(capability.json()["allowed"])

        adopt_res = self.teacher_client.post("/api/academic/schemes-of-work/adopt-published/", payload, format="json")
        self.assertEqual(adopt_res.status_code, status.HTTP_403_FORBIDDEN)

    # 6. Historical Integrity
    def test_changing_curriculum_assignment_next_year_preserves_old_scheme_provenance(self):
        # Year 2025: NERDC
        CurriculumAssignment.objects.create(
            academic_year=self.year_2025,
            curriculum=self.curriculum_nerdc,
            is_active=True,
        )
        scheme_2025 = SchemeOfWork.objects.create(
            academic_year=self.year_2025,
            term=self.term_1,
            curriculum_subject=self.nerdc_jss1_math,
            responsible_teacher=self.teacher,
            created_by=self.teacher_user,
            status=SchemeOfWorkStatus.APPROVED,
        )
        # Year 2026: Cambridge assigned
        CurriculumAssignment.objects.create(
            academic_year=self.year_2026,
            curriculum=self.curriculum_cambridge,
            is_active=True,
        )
        scheme_2025.refresh_from_db()
        self.assertEqual(scheme_2025.curriculum_subject.curriculum, self.curriculum_nerdc)
        self.assertEqual(scheme_2025.curriculum_subject.name, "NERDC JSS1 Mathematics")
