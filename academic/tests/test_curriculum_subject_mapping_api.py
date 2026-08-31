from django.urls import reverse
from rest_framework.test import APIClient

from academic.models import Curriculum, CurriculumSubject, GradeLevel, Subject, Teacher
from school.testcases import TenantTestCase
from tenants.models import TenantStatus
from users.models import CustomUser


class CurriculumSubjectMappingApiTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        super().setup_tenant(tenant)
        tenant.status = TenantStatus.ACTIVE

    def setUp(self):
        super().setUp()
        self.admin = CustomUser.objects.create_user(
            email="mapping-admin@school.test", password="x", is_admin=True
        )
        self.teacher_user = CustomUser.objects.create_user(
            email="mapping-teacher@school.test", password="x", is_teacher=True
        )
        Teacher.objects.create(user=self.teacher_user)
        self.admin_client = APIClient(HTTP_HOST=self.domain.domain)
        self.admin_client.force_authenticate(self.admin)
        self.teacher_client = APIClient(HTTP_HOST=self.domain.domain)
        self.teacher_client.force_authenticate(self.teacher_user)

        self.curriculum = Curriculum.objects.create(name="Early Years", version="2026")
        self.other_curriculum = Curriculum.objects.create(name="National", version="2025")
        self.grade = GradeLevel.objects.create(
            system_code="NUR_1", default_name="Nursery 1", section="NURSERY", sequence_order=1
        )
        self.other_grade = GradeLevel.objects.create(
            system_code="NUR_2", default_name="Nursery 2", section="NURSERY", sequence_order=2
        )
        self.literacy = CurriculumSubject.objects.create(
            curriculum=self.curriculum, grade_level=self.grade, name="Literacy", code="LIT"
        )
        self.health = CurriculumSubject.objects.create(
            curriculum=self.curriculum, grade_level=self.other_grade, name="Health Habits"
        )
        self.other = CurriculumSubject.objects.create(
            curriculum=self.other_curriculum, grade_level=self.grade, name="Numeracy"
        )
        self.english = Subject.objects.create(name="English Language", subject_code="ENG")
        self.language_arts = Subject.objects.create(name="Language Arts", subject_code="LAN")

    def mapping_url(self, curriculum_subject):
        return reverse("curriculum-subject-mapping", args=[curriculum_subject.id])

    def test_admin_can_map_change_and_unmap_without_changing_canonical_identity(self):
        original_name = self.literacy.name
        mapped = self.admin_client.patch(
            self.mapping_url(self.literacy), {"subject_id": self.english.id}, format="json"
        )
        self.assertEqual(mapped.status_code, 200, mapped.json())
        self.assertTrue(mapped.json()["is_mapped"])
        self.assertEqual(mapped.json()["subject_name"], "English Language")

        changed = self.admin_client.patch(
            self.mapping_url(self.literacy), {"subject_id": self.language_arts.id}, format="json"
        )
        self.assertEqual(changed.status_code, 200, changed.json())
        cleared = self.admin_client.patch(
            self.mapping_url(self.literacy), {"subject_id": None}, format="json"
        )
        self.assertEqual(cleared.status_code, 200, cleared.json())
        self.assertFalse(cleared.json()["is_mapped"])
        self.literacy.refresh_from_db()
        self.assertEqual(self.literacy.name, original_name)
        self.assertIsNone(self.literacy.subject)

    def test_mapping_rejects_invalid_subject_and_teacher_mutation(self):
        invalid = self.admin_client.patch(
            self.mapping_url(self.literacy), {"subject_id": 99999999}, format="json"
        )
        self.assertEqual(invalid.status_code, 400, invalid.json())
        unauthorized = self.teacher_client.patch(
            self.mapping_url(self.literacy), {"subject_id": self.english.id}, format="json"
        )
        self.assertEqual(unauthorized.status_code, 403, unauthorized.json())

    def test_list_exposes_mapping_metadata_and_filters(self):
        self.literacy.subject = self.english
        self.literacy.save(update_fields=["subject"])
        base = reverse("curriculum-subject-list")

        mapped = self.admin_client.get(base, {"mapped": "true"})
        unmapped = self.admin_client.get(base, {"mapped": "false"})
        by_curriculum = self.admin_client.get(base, {"curriculum": self.curriculum.id})
        by_grade = self.admin_client.get(base, {"grade_level": self.grade.id})
        searched = self.admin_client.get(base, {"search": "Literacy"})

        mapped_data = mapped.json()
        unmapped_data = unmapped.json()
        curriculum_data = by_curriculum.json()
        grade_data = by_grade.json()
        search_data = searched.json()
        self.assertEqual([row["id"] for row in mapped_data["results"]], [self.literacy.id])
        self.assertEqual(
            {row["id"] for row in unmapped_data["results"]},
            {self.health.id, self.other.id},
        )
        self.assertEqual(
            {row["id"] for row in curriculum_data["results"]},
            {self.literacy.id, self.health.id},
        )
        self.assertEqual(
            {row["id"] for row in grade_data["results"]},
            {self.literacy.id, self.other.id},
        )
        self.assertEqual([row["id"] for row in search_data["results"]], [self.literacy.id])
        self.assertEqual(search_data["results"][0]["curriculum_name"], "Early Years")
        self.assertEqual(search_data["results"][0]["grade_level_name"], "Nursery 1")
