from school.testcases import TenantTestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from academic.models import (
    Curriculum,
    CurriculumSubject,
    CurriculumGuidance,
    CurriculumTopic,
    GradeLevel,
    LearningObjective,
    SectionType,
    StandardClassCode,
    Subject,
    Topic,
)


from tenants.models import TenantStatus


class CurriculumClassesApiTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        super().setup_tenant(tenant)
        tenant.status = TenantStatus.ACTIVE

    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.user = User.objects.create_user(
            email="admin@test.com",
            password="password123",
            is_admin=True,
        )
        self.client = APIClient(HTTP_HOST=self.domain.domain)
        self.client.force_authenticate(user=self.user)

        self.curriculum = Curriculum.objects.create(
            name="National Standard Curriculum",
            version="2025",
            is_active=True,
        )
        self.other_curriculum = Curriculum.objects.create(
            name="Cambridge International",
            version="2025",
            is_active=True,
        )

        self.grade_nursery = GradeLevel.objects.create(
            system_code=StandardClassCode.NURSERY_1,
            default_name="Nursery 1",
            alias="EYFS 1",
            section=SectionType.PRE_PRIMARY,
            sequence_order=1,
        )
        self.grade_basic1 = GradeLevel.objects.create(
            system_code=StandardClassCode.BASIC_1,
            default_name="Basic 1",
            alias="Grade 1",
            section=SectionType.PRIMARY,
            sequence_order=2,
            graduation_note="Primary Foundation",
        )
        self.grade_jss1 = GradeLevel.objects.create(
            system_code=StandardClassCode.JSS_1,
            default_name="JSS 1",
            alias="Year 7",
            section=SectionType.JUNIOR_SECONDARY,
            sequence_order=3,
        )
        self.grade_unused = GradeLevel.objects.create(
            system_code=StandardClassCode.SS_1,
            default_name="SS 1",
            section=SectionType.SENIOR_SECONDARY,
            sequence_order=4,
        )

        self.math = Subject.objects.create(name="Mathematics", subject_code="MTH")
        self.english = Subject.objects.create(name="English Language", subject_code="ENG")
        self.science = Subject.objects.create(name="Basic Science", subject_code="SCI")

        # Map 2 subjects to Basic 1, 1 subject to JSS 1 in self.curriculum
        self.math_mapping = CurriculumSubject.objects.create(
            curriculum=self.curriculum,
            grade_level=self.grade_basic1,
            subject=self.math,
        )
        self.english_mapping = CurriculumSubject.objects.create(
            curriculum=self.curriculum,
            grade_level=self.grade_basic1,
            subject=self.english,
        )
        CurriculumSubject.objects.create(
            curriculum=self.curriculum,
            grade_level=self.grade_jss1,
            subject=self.science,
        )

        # Map 1 subject in other_curriculum
        CurriculumSubject.objects.create(
            curriculum=self.other_curriculum,
            grade_level=self.grade_nursery,
            subject=self.math,
        )

    def test_get_curriculum_classes_returns_only_classes_for_that_curriculum(self):
        url = f"/api/academic/curricula/{self.curriculum.id}/classes/"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        results = data.get("results", data)

        # Should only have Basic 1 and JSS 1 (not Nursery 1 or SS 1)
        self.assertEqual(len(results), 2)
        
        # Verify ordering by sequence_order
        self.assertEqual(results[0]["id"], self.grade_basic1.id)
        self.assertEqual(results[0]["default_name"], "Basic 1")
        self.assertEqual(results[0]["alias"], "Grade 1")
        self.assertEqual(results[0]["subjects_count"], 2)
        self.assertEqual(results[0]["graduation_note"], "Primary Foundation")

        self.assertEqual(results[1]["id"], self.grade_jss1.id)
        self.assertEqual(results[1]["default_name"], "JSS 1")
        self.assertEqual(results[1]["subjects_count"], 1)

    def test_curriculum_classes_for_empty_curriculum(self):
        empty_curriculum = Curriculum.objects.create(name="Empty Curriculum")
        url = f"/api/academic/curricula/{empty_curriculum.id}/classes/"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        results = data.get("results", data)
        self.assertEqual(len(results), 0)

    def test_curriculum_list_returns_grade_levels_and_no_subjects(self):
        url = "/api/academic/curricula/"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        results = data.get("results", data)

        curr_data = next((c for c in results if c["id"] == self.curriculum.id), None)
        self.assertIsNotNone(curr_data)
        # Verify subjects is removed
        self.assertNotIn("subjects", curr_data)
        # Verify grade_levels is present and contains the names in sequence order
        self.assertEqual(curr_data["grade_levels"], ["Grade 1", "Year 7"])

    def test_grade_level_subjects_returns_lightweight_annotated_summaries(self):
        topic = Topic.objects.create(
            name="Number Concepts",
            grade_level=self.grade_basic1,
            subject=self.math,
        )
        curriculum_topic = CurriculumTopic.objects.create(
            curriculum_subject=self.math_mapping,
            topic=topic,
            theme="Number and Numeration",
            order=1,
        )
        LearningObjective.objects.create(
            curriculum_topic=curriculum_topic,
            description="Recognise whole numbers.",
            order=1,
        )

        url = (
            f"/api/academic/curricula/{self.curriculum.id}/classes/"
            f"{self.grade_basic1.id}/subjects/"
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json().get("results", response.json())
        self.assertEqual([item["name"] for item in results], ["English Language", "Mathematics"])
        math = next(item for item in results if item["name"] == "Mathematics")
        self.assertEqual(math["id"], self.math_mapping.id)
        self.assertEqual(math["code"], "MTH")
        self.assertEqual(math["themes_count"], 1)
        self.assertEqual(math["topics_count"], 1)
        self.assertEqual(math["objectives_count"], 1)
        self.assertNotIn("topics", math)
        self.assertNotIn("learning_objectives", math)

    def test_grade_level_subjects_rejects_grade_from_another_curriculum(self):
        url = (
            f"/api/academic/curricula/{self.curriculum.id}/classes/"
            f"{self.grade_nursery.id}/subjects/"
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_subject_content_returns_lightweight_topic_summaries(self):
        topic = Topic.objects.create(
            name="Number Concepts",
            grade_level=self.grade_basic1,
            subject=self.math,
        )
        topic.subtopics.create(name="Whole Numbers")
        curriculum_topic = CurriculumTopic.objects.create(
            curriculum_subject=self.math_mapping,
            topic=topic,
            theme="Number and Numeration",
            order=1,
        )
        LearningObjective.objects.create(
            curriculum_topic=curriculum_topic,
            description="Recognise whole numbers.",
            order=1,
        )
        url = (
            f"/api/academic/curricula/{self.curriculum.id}/classes/"
            f"{self.grade_basic1.id}/subjects/{self.math_mapping.id}/content/"
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json().get("results", response.json())
        self.assertEqual(len(results), 1)
        summary = results[0]
        self.assertEqual(summary["id"], curriculum_topic.id)
        self.assertEqual(summary["topic_id"], topic.id)
        self.assertEqual(summary["name"], "Number Concepts")
        self.assertEqual(summary["theme"], "Number and Numeration")
        self.assertEqual(summary["subtopics_count"], 1)
        self.assertEqual(summary["objectives_count"], 1)
        self.assertFalse(summary["has_guidance"])
        self.assertNotIn("content_summary", summary)
        self.assertNotIn("learning_objectives", summary)
        self.assertNotIn("guidance", summary)

    def test_subject_content_rejects_mapping_outside_requested_hierarchy(self):
        url = (
            f"/api/academic/curricula/{self.other_curriculum.id}/classes/"
            f"{self.grade_nursery.id}/subjects/{self.math_mapping.id}/content/"
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_topic_detail_returns_full_content_and_validates_hierarchy(self):
        topic = Topic.objects.create(name="Fractions", grade_level=self.grade_basic1, subject=self.math)
        topic.subtopics.create(name="Proper Fractions")
        mapping = CurriculumTopic.objects.create(
            curriculum_subject=self.math_mapping, topic=topic, theme="Numbers",
            content_summary="Meaning and types of fractions", order=1,
        )
        LearningObjective.objects.create(
            curriculum_topic=mapping, description="Identify proper fractions", order=1,
        )
        CurriculumGuidance.objects.create(
            curriculum_topic=mapping, teacher_activities="Demonstrate with shapes",
        )
        url = (
            f"/api/academic/curricula/{self.curriculum.id}/classes/{self.grade_basic1.id}/"
            f"subjects/{self.math_mapping.id}/topics/{mapping.id}/"
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["name"], "Fractions")
        self.assertEqual(data["content_summary"], "Meaning and types of fractions")
        self.assertEqual(len(data["subtopics"]), 1)
        self.assertEqual(len(data["learning_objectives"]), 1)
        self.assertEqual(data["guidance"]["teacher_activities"], "Demonstrate with shapes")

        wrong_url = (
            f"/api/academic/curricula/{self.other_curriculum.id}/classes/{self.grade_basic1.id}/"
            f"subjects/{self.math_mapping.id}/topics/{mapping.id}/"
        )
        self.assertEqual(self.client.get(wrong_url).status_code, status.HTTP_404_NOT_FOUND)
