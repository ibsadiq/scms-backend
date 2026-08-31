from academic.models import Curriculum, CurriculumSubject, CurriculumTopic, GradeLevel, Subject
from academic.services.curriculum_import_service import CurriculumImportError, CurriculumImportService
from school.testcases import TenantTestCase
from scripts.import_curriculum_content import ensure_curriculum_subject_mappings


class CurriculumImportScriptDecouplingTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.grade = GradeLevel.objects.create(
            system_code="NUR_1",
            default_name="Nursery 1",
            section="NURSERY",
            sequence_order=1,
        )
        self.curriculum = Curriculum.objects.create(
            name="NAPPS Curriculum",
            version="2026",
            is_active=True,
        )

    def payload(self, *, schema_version="2.0", subject="Health Habits"):
        data = {
            "curriculum": {
                "name": self.curriculum.name,
                "version": self.curriculum.version,
            },
            "source": {"title": "NAPPS canonical source"},
            "grades": [{
                "grade": self.grade.system_code,
                "subjects": [{
                    "subject": subject,
                    "topics": [{
                        "name": "Healthy Routines",
                        "topic_key": "healthy-routines",
                        "theme": "Personal Health",
                        "order": 1,
                        "content_summary": "",
                        "subtopics": [],
                        "learning_objectives": [],
                        "guidance": None,
                    }],
                    "published_schemes": [],
                    "resources": [],
                }],
            }],
        }
        if schema_version is not None:
            data["schema_version"] = schema_version
        return data

    def ensure(self, data):
        return ensure_curriculum_subject_mappings(
            data=data,
            curriculum=self.curriculum,
            grade_filter=None,
            subject_filter=None,
        )

    def test_v2_precreation_and_import_succeed_with_zero_operational_subjects(self):
        self.assertEqual(Subject.objects.count(), 0)
        data = self.payload()

        self.assertEqual(self.ensure(data), (1, 0, 0))
        canonical = CurriculumSubject.objects.get()
        self.assertEqual(canonical.name, "Health Habits")
        self.assertEqual(canonical.code, "")
        self.assertIsNone(canonical.subject)

        CurriculumImportService.import_content(data=data, curriculum=self.curriculum)
        canonical.refresh_from_db()
        self.assertIsNone(canonical.subject)
        self.assertTrue(
            CurriculumTopic.objects.filter(
                curriculum_subject=canonical,
                name="Healthy Routines",
                topic__isnull=True,
            ).exists()
        )
        self.assertEqual(Subject.objects.count(), 0)

    def test_repeated_precreation_is_idempotent(self):
        data = self.payload()
        self.assertEqual(self.ensure(data), (1, 0, 0))
        self.assertEqual(self.ensure(data), (0, 1, 0))
        self.assertEqual(CurriculumSubject.objects.count(), 1)

    def test_existing_operational_subject_is_optional_enrichment(self):
        data = self.payload(subject="Health Habits")
        self.ensure(data)
        canonical = CurriculumSubject.objects.get()
        self.assertIsNone(canonical.subject)

        operational = Subject.objects.create(name="Health Habits", subject_code="HLTH")
        self.assertEqual(self.ensure(data), (0, 1, 0))
        canonical.refresh_from_db()
        self.assertEqual(canonical.subject, operational)
        self.assertEqual(canonical.name, "Health Habits")
        self.assertEqual(canonical.code, "HLTH")

    def test_v1_precreation_retains_operational_subject_requirement(self):
        data = self.payload(schema_version=None)
        with self.assertRaises(CurriculumImportError):
            self.ensure(data)
        self.assertEqual(CurriculumSubject.objects.count(), 0)
