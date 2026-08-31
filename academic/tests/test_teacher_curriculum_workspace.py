from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from academic.models import (
    AllocatedSubject,
    ClassRoom,
    Curriculum,
    CurriculumAssignment,
    CurriculumGuidance,
    CurriculumResource,
    CurriculumResourceType,
    CurriculumSubject,
    CurriculumTopic,
    GradeLevel,
    LearningObjective,
    PublishedScheme,
    PublishedSchemeEntry,
    SectionType,
    StandardClassCode,
    Subject,
    SubTopic,
    Teacher,
    Topic,
)
from administration.models import AcademicYear, Term
from school.testcases import TenantTestCase
from tenants.models import TenantStatus


class TeacherCurriculumWorkspaceTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        super().setup_tenant(tenant)
        tenant.status = TenantStatus.ACTIVE

    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.teacher_user = User.objects.create_user(
            email="teacher_t2_1@test.com",
            password="password123",
            is_teacher=True,
        )
        self.other_teacher_user = User.objects.create_user(
            email="teacher_t2_2@test.com",
            password="password123",
            is_teacher=True,
        )
        self.admin_user = User.objects.create_user(
            email="admin_t2@test.com",
            password="password123",
            is_admin=True,
        )

        self.teacher = Teacher.objects.create(user=self.teacher_user)
        self.other_teacher = Teacher.objects.create(user=self.other_teacher_user)

        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-07-31",
            active_year=True,
        )
        self.term = Term.objects.create(
            academic_year=self.year,
            name="First Term",
            start_date="2025-09-01",
            end_date="2025-12-15",
        )

        self.grade_jss1 = GradeLevel.objects.create(
            system_code=StandardClassCode.JSS_1,
            default_name="JSS 1",
            section=SectionType.JUNIOR_SECONDARY,
            sequence_order=7,
        )
        self.grade_jss2 = GradeLevel.objects.create(
            system_code=StandardClassCode.JSS_2,
            default_name="JSS 2",
            section=SectionType.JUNIOR_SECONDARY,
            sequence_order=8,
        )

        self.classroom_jss1a = ClassRoom.objects.create(
            grade_level=self.grade_jss1,
            name="JSS 1A",
            capacity=40,
        )
        self.classroom_jss1b = ClassRoom.objects.create(
            grade_level=self.grade_jss1,
            name="JSS 1B",
            capacity=40,
        )

        self.subject_math = Subject.objects.create(name="Mathematics", subject_code="MTH")
        self.subject_eng = Subject.objects.create(name="English Language", subject_code="ENG")

        # Curricula
        self.curr_nerdc = Curriculum.objects.create(
            name="NERDC National Curriculum",
            version="2025",
            authority_name="NERDC",
            authority_type="NATIONAL",
            description="Official Nigerian Basic Education Curriculum",
            is_active=True,
        )
        self.curr_cambridge = Curriculum.objects.create(
            name="Cambridge Lower Secondary",
            version="2024",
            authority_name="Cambridge",
            authority_type="INTERNATIONAL",
            description="Cambridge International Curriculum",
            is_active=True,
        )

        # Mapped CurriculumSubjects
        self.cs_nerdc_math = CurriculumSubject.objects.create(
            curriculum=self.curr_nerdc,
            grade_level=self.grade_jss1,
            subject=self.subject_math,
            name="Junior Secondary Mathematics",
            code="MTH-J1",
            is_active=True,
        )
        self.cs_nerdc_eng = CurriculumSubject.objects.create(
            curriculum=self.curr_nerdc,
            grade_level=self.grade_jss1,
            subject=self.subject_eng,
            name="Junior Secondary English",
            code="ENG-J1",
            is_active=True,
        )
        self.cs_cambridge_math = CurriculumSubject.objects.create(
            curriculum=self.curr_cambridge,
            grade_level=self.grade_jss1,
            subject=self.subject_math,
            name="Cambridge Checkpoint Mathematics",
            code="CAM-M1",
            is_active=True,
        )

        # Canonical Topic 1 (with Theme, Guidance, M2M Subtopics, and Learning Objectives)
        self.topic1 = CurriculumTopic.objects.create(
            curriculum_subject=self.cs_nerdc_math,
            name="Number and Numeration",
            theme="Number Theory",
            content_summary="Whole numbers, Place Value, LCM and HCF",
            order=1,
            is_active=True,
        )
        self.guidance1 = CurriculumGuidance.objects.create(
            curriculum_topic=self.topic1,
            teacher_activities="Demonstrate with charts and base ten blocks.",
            learner_activities="Count and factorize numbers in pairs.",
            teaching_learning_materials="Abacus, Place Value charts",
            evaluation_guide="Evaluate ability to compute LCM and HCF.",
            notes="Emphasize prime factor tree method.",
        )
        self.subtopic1 = SubTopic.objects.create(name="Whole Numbers up to 1 Billion", is_active=True)
        self.subtopic2 = SubTopic.objects.create(name="LCM and HCF of 2-digit numbers", is_active=True)
        self.subtopic_inactive = SubTopic.objects.create(name="Archived SubTopic", is_active=False)
        self.topic1.subtopics.add(self.subtopic1, self.subtopic2, self.subtopic_inactive)

        # Objective with subtopic
        self.obj1 = LearningObjective.objects.create(
            curriculum_topic=self.topic1,
            subtopic=self.subtopic1,
            description="Read and write whole numbers up to one billion in words and figures.",
            order=1,
            is_active=True,
        )
        # Objective with NULL subtopic (must NOT disappear)
        self.obj2 = LearningObjective.objects.create(
            curriculum_topic=self.topic1,
            subtopic=None,
            description="Appreciate the significance of place value in real-life transactions.",
            order=2,
            is_active=True,
        )
        # Inactive objective (must be filtered out)
        self.obj_inactive = LearningObjective.objects.create(
            curriculum_topic=self.topic1,
            subtopic=self.subtopic2,
            description="Inactive objective placeholder.",
            order=3,
            is_active=False,
        )

        # Canonical Topic 2
        self.topic2 = CurriculumTopic.objects.create(
            curriculum_subject=self.cs_nerdc_math,
            name="Basic Operations",
            theme="Arithmetic",
            order=2,
            is_active=True,
        )
        self.subtopic_shared = SubTopic.objects.create(name="Addition and Subtraction of Directed Numbers", is_active=True)
        self.topic2.subtopics.add(self.subtopic_shared)
        # Also test sharing subtopic with topic1 to verify M2M decoupled architecture
        self.topic1.subtopics.add(self.subtopic_shared)

        self.obj3 = LearningObjective.objects.create(
            curriculum_topic=self.topic2,
            subtopic=self.subtopic_shared,
            description="Perform basic operations with signed numbers.",
            order=1,
            is_active=True,
        )

        # Unrelated Topic under Cambridge Math (must NOT be returned for NERDC)
        self.cam_topic = CurriculumTopic.objects.create(
            curriculum_subject=self.cs_cambridge_math,
            name="Cambridge Algebra Fundamentals",
            order=1,
            is_active=True,
        )

        # Published Scheme under NERDC Math
        self.scheme1 = PublishedScheme.objects.create(
            curriculum_subject=self.cs_nerdc_math,
            name="NERDC Official Scheme 2025/2026",
            version="1.0",
            description="Standard term-by-term plan for JSS 1 Mathematics",
            is_active=True,
        )
        self.scheme_entry1 = PublishedSchemeEntry.objects.create(
            published_scheme=self.scheme1,
            term_number=1,
            week_start=1,
            week_end=2,
            title="Whole Numbers & Place Value",
            curriculum_topic=self.topic1,
            is_active=True,
        )
        self.scheme_entry2 = PublishedSchemeEntry.objects.create(
            published_scheme=self.scheme1,
            term_number=2,
            week_start=1,
            week_end=2,
            title="Directed Numbers",
            curriculum_topic=self.topic2,
            is_active=True,
        )
        # Unrelated scheme for Cambridge
        self.cam_scheme = PublishedScheme.objects.create(
            curriculum_subject=self.cs_cambridge_math,
            name="Cambridge Checkpoint Scheme",
            version="2024",
            is_active=True,
        )

        # Curriculum Resources for NERDC Math
        self.res1 = CurriculumResource.objects.create(
            curriculum_subject=self.cs_nerdc_math,
            curriculum_topic=self.topic1,
            resource_type=CurriculumResourceType.INSTRUCTIONAL_NOTE,
            title="Teacher Guide on Place Value & Factorization",
            content="Use visual charts and abacus models.",
            metadata={"isbn": "978-0-12345-678-9"},
            is_active=True,
        )
        self.res2 = CurriculumResource.objects.create(
            curriculum_subject=self.cs_nerdc_math,
            curriculum_topic=None,
            resource_type=CurriculumResourceType.REFERENCE,
            title="Essential Mathematics for Junior Secondary Schools 1",
            metadata={"publisher": "NERDC Press"},
            is_active=True,
        )
        # Inactive resource
        self.res_inactive = CurriculumResource.objects.create(
            curriculum_subject=self.cs_nerdc_math,
            curriculum_topic=self.topic1,
            resource_type=CurriculumResourceType.ASSIGNMENT,
            title="Deprecated Worksheet",
            is_active=False,
        )
        # Unrelated resource for Cambridge
        self.cam_resource = CurriculumResource.objects.create(
            curriculum_subject=self.cs_cambridge_math,
            title="Cambridge Math Workbook",
            is_active=True,
        )

        # Allocations
        self.alloc_math_teacher1 = AllocatedSubject.objects.create(
            teacher_name=self.teacher,
            class_room=self.classroom_jss1a,
            subject=self.subject_math,
            academic_year=self.year,
            term=self.term,
            weekly_periods=4,
        )
        self.alloc_math_teacher2 = AllocatedSubject.objects.create(
            teacher_name=self.other_teacher,
            class_room=self.classroom_jss1b,
            subject=self.subject_math,
            academic_year=self.year,
            term=self.term,
            weekly_periods=4,
        )
        self.alloc_eng_teacher1 = AllocatedSubject.objects.create(
            teacher_name=self.teacher,
            class_room=self.classroom_jss1a,
            subject=self.subject_eng,
            academic_year=self.year,
            term=self.term,
            weekly_periods=4,
        )

        # School-wide Assignment: NERDC for this academic year
        self.assign_nerdc = CurriculumAssignment.objects.create(
            academic_year=self.year,
            curriculum=self.curr_nerdc,
            is_active=True,
        )

        self.client_teacher = APIClient(HTTP_HOST=self.domain.domain)
        self.client_teacher.force_authenticate(user=self.teacher_user)

        self.client_other_teacher = APIClient(HTTP_HOST=self.domain.domain)
        self.client_other_teacher.force_authenticate(user=self.other_teacher_user)

        self.client_admin = APIClient(HTTP_HOST=self.domain.domain)
        self.client_admin.force_authenticate(user=self.admin_user)

    def test_teacher_can_load_curriculum_for_own_allocation(self):
        """Teacher can load resolved curriculum for own teaching allocation."""
        url = f"/api/academic/allocated-subjects/{self.alloc_math_teacher1.id}/curriculum/"
        response = self.client_teacher.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(data["status"], "RESOLVED")
        self.assertIsNone(data["message"])

        # Allocation summary
        self.assertEqual(data["allocation"]["id"], self.alloc_math_teacher1.id)
        self.assertEqual(data["allocation"]["subject_name"], "Mathematics")
        self.assertEqual(data["allocation"]["classroom_name"], "JSS 1A")
        self.assertEqual(data["allocation"]["grade_level_name"], "JSS 1")

        # Canonical Curriculum & Subject
        self.assertEqual(data["curriculum"]["id"], self.curr_nerdc.id)
        self.assertEqual(data["curriculum"]["name"], "NERDC National Curriculum")
        self.assertEqual(data["curriculum"]["authority_name"], "NERDC")
        self.assertEqual(data["curriculum"]["version"], "2025")

        self.assertEqual(data["curriculum_subject"]["id"], self.cs_nerdc_math.id)
        self.assertEqual(data["curriculum_subject"]["name"], "Junior Secondary Mathematics")
        self.assertEqual(data["curriculum_subject"]["code"], "MTH-J1")

        # Topics
        self.assertEqual(len(data["topics"]), 2)
        t1 = data["topics"][0]
        self.assertEqual(t1["name"], "Number and Numeration")
        self.assertEqual(t1["theme"], "Number Theory")
        self.assertEqual(t1["order"], 1)
        self.assertEqual(t1["resource_count"], 1)

        # M2M Subtopics (active only, ordered)
        subtopic_names = [st["name"] for st in t1["subtopics"]]
        self.assertIn("Whole Numbers up to 1 Billion", subtopic_names)
        self.assertIn("LCM and HCF of 2-digit numbers", subtopic_names)
        self.assertIn("Addition and Subtraction of Directed Numbers", subtopic_names)
        self.assertNotIn("Archived SubTopic", subtopic_names)

        # Learning Objectives (including subtopic=None objective)
        self.assertEqual(len(t1["learning_objectives"]), 2)
        obj1 = t1["learning_objectives"][0]
        self.assertEqual(obj1["description"], "Read and write whole numbers up to one billion in words and figures.")
        self.assertEqual(obj1["subtopic_name"], "Whole Numbers up to 1 Billion")

        obj2 = t1["learning_objectives"][1]
        self.assertEqual(obj2["description"], "Appreciate the significance of place value in real-life transactions.")
        self.assertIsNone(obj2["subtopic_id"])
        self.assertIsNone(obj2["subtopic_name"])

        # Guidance
        self.assertIsNotNone(t1["guidance"])
        self.assertEqual(t1["guidance"]["teacher_activities"], "Demonstrate with charts and base ten blocks.")
        self.assertEqual(t1["guidance"]["notes"], "Emphasize prime factor tree method.")

        # Published Scheme summary
        self.assertEqual(len(data["published_schemes"]), 1)
        scheme = data["published_schemes"][0]
        self.assertEqual(scheme["id"], self.scheme1.id)
        self.assertEqual(scheme["name"], "NERDC Official Scheme 2025/2026")
        self.assertEqual(scheme["entry_count"], 2)
        self.assertEqual(scheme["term_coverage"], [1, 2])

        # Resources (active only, scoped to NERDC Math)
        self.assertEqual(len(data["resources"]), 2)
        resource_titles = [r["title"] for r in data["resources"]]
        self.assertIn("Teacher Guide on Place Value & Factorization", resource_titles)
        self.assertIn("Essential Mathematics for Junior Secondary Schools 1", resource_titles)
        self.assertNotIn("Deprecated Worksheet", resource_titles)
        self.assertNotIn("Cambridge Math Workbook", resource_titles)

    def test_teacher_cannot_load_another_teachers_allocation(self):
        """Teacher A cannot load curriculum for Teacher B's allocation (returns 404)."""
        url = f"/api/academic/allocated-subjects/{self.alloc_math_teacher2.id}/curriculum/"
        response = self.client_teacher.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_curriculum_or_subject_query_parameters_cannot_override_resolution(self):
        """Query parameters such as curriculum_subject_id cannot override deterministic resolution."""
        # Teacher attempts to pass Cambridge subject ID in query parameters
        url = (
            f"/api/academic/allocated-subjects/{self.alloc_math_teacher1.id}/curriculum/"
            f"?curriculum_id={self.curr_cambridge.id}&curriculum_subject_id={self.cs_cambridge_math.id}"
        )
        response = self.client_teacher.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        # Must still resolve to NERDC Mathematics based on assignment, ignoring query params
        self.assertEqual(data["curriculum"]["id"], self.curr_nerdc.id)
        self.assertEqual(data["curriculum_subject"]["id"], self.cs_nerdc_math.id)

    def test_admin_can_access_any_allocation_curriculum(self):
        """School Admin can view curriculum workspace for any allocation."""
        url = f"/api/academic/allocated-subjects/{self.alloc_math_teacher2.id}/curriculum/"
        response = self.client_admin.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["status"], "RESOLVED")
        self.assertEqual(data["allocation"]["id"], self.alloc_math_teacher2.id)

    def test_no_curriculum_assigned_returns_200_with_status(self):
        """When no active assignment exists, returns 200 with NO_CURRICULUM_ASSIGNED contract."""
        self.assign_nerdc.is_active = False
        self.assign_nerdc.save()

        url = f"/api/academic/allocated-subjects/{self.alloc_math_teacher1.id}/curriculum/"
        response = self.client_teacher.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(data["status"], "NO_CURRICULUM_ASSIGNED")
        self.assertIn("not assigned a curriculum framework", data["message"])
        self.assertIsNone(data["curriculum"])
        self.assertIsNone(data["curriculum_subject"])
        self.assertEqual(data["topics"], [])
        self.assertEqual(data["published_schemes"], [])
        self.assertEqual(data["resources"], [])

    def test_subject_unmapped_returns_200_with_status_and_curriculum_info(self):
        """When curriculum is assigned but subject is not mapped, returns 200 with SUBJECT_UNMAPPED."""
        # Unmap English Language from NERDC
        self.cs_nerdc_eng.subject = None
        self.cs_nerdc_eng.save()

        url = f"/api/academic/allocated-subjects/{self.alloc_eng_teacher1.id}/curriculum/"
        response = self.client_teacher.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(data["status"], "SUBJECT_UNMAPPED")
        self.assertIn("not been mapped", data["message"])
        self.assertIsNotNone(data["curriculum"])
        self.assertEqual(data["curriculum"]["id"], self.curr_nerdc.id)
        self.assertEqual(data["curriculum"]["name"], "NERDC National Curriculum")
        self.assertIsNone(data["curriculum_subject"])
        self.assertEqual(data["topics"], [])

    def test_configuration_conflict_returns_200_with_status(self):
        """When multiple conflicting mappings exist under the assigned curriculum, returns CONFIGURATION_CONFLICT."""
        # Create a second conflicting CurriculumSubject for math under NERDC
        CurriculumSubject.objects.create(
            curriculum=self.curr_nerdc,
            grade_level=self.grade_jss1,
            subject=self.subject_math,
            name="Conflicting Additional Math",
            is_active=True,
        )

        url = f"/api/academic/allocated-subjects/{self.alloc_math_teacher1.id}/curriculum/"
        response = self.client_teacher.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(data["status"], "CONFIGURATION_CONFLICT")
        self.assertIn("cannot currently be resolved safely", data["message"])
        self.assertIsNone(data["curriculum_subject"])

    def test_empty_canonical_topics_and_resources_handled_cleanly(self):
        """When curriculum subject is resolved but has no topics, schemes, or resources, returns clean empty lists."""
        url = f"/api/academic/allocated-subjects/{self.alloc_eng_teacher1.id}/curriculum/"
        response = self.client_teacher.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(data["status"], "RESOLVED")
        self.assertEqual(data["curriculum_subject"]["name"], "Junior Secondary English")
        self.assertEqual(data["topics"], [])
        self.assertEqual(data["published_schemes"], [])
        self.assertEqual(data["resources"], [])

    def test_unrelated_curriculum_content_is_strictly_excluded(self):
        """Topics, schemes, and resources from other subjects/curricula are not leaked."""
        url = f"/api/academic/allocated-subjects/{self.alloc_math_teacher1.id}/curriculum/"
        response = self.client_teacher.get(url)
        data = response.json()

        # Cambridge topic must not be present
        topic_names = [t["name"] for t in data["topics"]]
        self.assertNotIn("Cambridge Algebra Fundamentals", topic_names)

        # Cambridge scheme must not be present
        scheme_names = [s["name"] for s in data["published_schemes"]]
        self.assertNotIn("Cambridge Checkpoint Scheme", scheme_names)

        # Cambridge resource must not be present
        resource_titles = [r["title"] for r in data["resources"]]
        self.assertNotIn("Cambridge Math Workbook", resource_titles)
