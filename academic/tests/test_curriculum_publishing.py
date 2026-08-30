from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework.test import APIClient

from school.testcases import TenantTestCase
from users.models import CustomUser
from tenants.models import TenantStatus

from academic.models import (
    Curriculum,
    CurriculumImportBatch,
    CurriculumResource,
    CurriculumResourceType,
    CurriculumSource,
    CurriculumSubject,
    CurriculumTopic,
    GradeLevel,
    LearningObjective,
    PublishedScheme,
    PublishedSchemeEntry,
    PublishedSchemeEntryType,
    SourceType,
    Subject,
    SubTopic,
    Topic,
)
from academic.services import CurriculumResourceService, PublishedSchemeService


class CurriculumPublishingTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        super().setup_tenant(tenant)
        tenant.status = TenantStatus.ACTIVE

    def setUp(self):
        super().setUp()
        self.user = CustomUser.objects.create_user(
            email="publisher@test.com", password=None, is_admin=True
        )
        self.grade = GradeLevel.objects.create(
            system_code="SS_1",
            default_name="SS 1",
            alias="Year 10",
            section="SSS",
            sequence_order=15,
        )
        self.math = Subject.objects.create(
            name="Mathematics", subject_code="MATH-PUB", graded=True
        )
        self.chemistry = Subject.objects.create(
            name="Chemistry", subject_code="CHEM-PUB", graded=True
        )
        self.curriculum = Curriculum.objects.create(
            name="NERDC Publishing Test", version="2025"
        )
        self.math_subject = CurriculumSubject.objects.create(
            curriculum=self.curriculum, subject=self.math, grade_level=self.grade
        )
        self.chemistry_subject = CurriculumSubject.objects.create(
            curriculum=self.curriculum, subject=self.chemistry, grade_level=self.grade
        )
        self.math_topic = Topic.objects.create(
            name="Algebra", subject=self.math, grade_level=self.grade
        )
        self.chemistry_topic = Topic.objects.create(
            name="Introduction to Chemistry", subject=self.chemistry, grade_level=self.grade
        )
        self.math_mapping = CurriculumTopic.objects.create(
            curriculum_subject=self.math_subject, topic=self.math_topic, order=1
        )
        self.chemistry_mapping = CurriculumTopic.objects.create(
            curriculum_subject=self.chemistry_subject, topic=self.chemistry_topic, order=1
        )
        self.math_subtopic = SubTopic.objects.create(name="Linear equations", topic=self.math_topic)
        self.chemistry_subtopic = SubTopic.objects.create(name="History", topic=self.chemistry_topic)
        self.math_objective = LearningObjective.objects.create(
            curriculum_topic=self.math_mapping, description="Solve equations", order=1
        )
        self.chemistry_objective = LearningObjective.objects.create(
            curriculum_topic=self.chemistry_mapping, description="Explain chemistry history", order=1
        )
        self.source = CurriculumSource.objects.create(
            curriculum=self.curriculum,
            title="NERDC 2025",
            source_type=SourceType.PDF,
        )
        self.batch = CurriculumImportBatch.objects.create(
            curriculum=self.curriculum, source=self.source
        )
        self.scheme = PublishedSchemeService.save_scheme(
            curriculum_subject=self.chemistry_subject,
            name="NERDC Scheme of Work",
            version="2025",
            source=self.source,
        )

    def test_published_scheme_has_no_school_year_or_term_and_supports_versions(self):
        self.assertFalse(hasattr(self.scheme, "academic_year"))
        self.assertFalse(hasattr(self.scheme, "term"))
        second = PublishedSchemeService.save_scheme(
            curriculum_subject=self.chemistry_subject,
            name="NERDC Scheme of Work",
            version="2026",
        )
        self.assertNotEqual(self.scheme.pk, second.pk)

    def test_published_scheme_uniqueness(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PublishedScheme.objects.create(
                curriculum_subject=self.chemistry_subject,
                name=self.scheme.name,
                version=self.scheme.version,
            )

    def test_valid_single_week_range_and_repeated_topic(self):
        first = PublishedSchemeService.save_entry(
            published_scheme=self.scheme,
            term_number=1,
            week_start=1,
            curriculum_topic=self.chemistry_mapping,
            title="Introduction",
            order=1,
            subtopics=[self.chemistry_subtopic],
            learning_objectives=[self.chemistry_objective],
        )
        ranged = PublishedSchemeService.save_entry(
            published_scheme=self.scheme,
            term_number=1,
            week_start=7,
            week_end=10,
            curriculum_topic=self.chemistry_mapping,
            title="Continuation",
            order=2,
        )
        same_week = PublishedSchemeService.save_entry(
            published_scheme=self.scheme,
            term_number=1,
            week_start=1,
            curriculum_topic=self.chemistry_mapping,
            title="Practical",
            order=3,
        )
        self.assertEqual(first.week_start, 1)
        self.assertEqual((ranged.week_start, ranged.week_end), (7, 10))
        self.assertEqual(same_week.week_start, first.week_start)

    def test_break_entry_may_omit_topic_and_week(self):
        entry = PublishedSchemeService.save_entry(
            published_scheme=self.scheme,
            term_number=2,
            entry_type=PublishedSchemeEntryType.BREAK,
            title="Midterm Break",
            order=1,
        )
        self.assertIsNone(entry.curriculum_topic)
        self.assertIsNone(entry.week_start)

    def test_invalid_term_week_range_and_topic_scope(self):
        cases = [
            {"term_number": 4, "week_start": 1},
            {"term_number": 1, "week_start": 0},
            {"term_number": 1, "week_start": 10, "week_end": 7},
            {"term_number": 1, "week_start": 1, "curriculum_topic": self.math_mapping},
        ]
        for index, values in enumerate(cases, start=1):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                PublishedSchemeService.save_entry(
                    published_scheme=self.scheme, order=index, **values
                )

    def test_unrelated_subtopic_and_objective_are_rejected(self):
        with self.assertRaises(ValidationError):
            PublishedSchemeService.save_entry(
                published_scheme=self.scheme,
                term_number=1,
                week_start=1,
                curriculum_topic=self.chemistry_mapping,
                order=1,
                subtopics=[self.math_subtopic],
            )
        with self.assertRaises(ValidationError):
            PublishedSchemeService.save_entry(
                published_scheme=self.scheme,
                term_number=1,
                week_start=1,
                curriculum_topic=self.chemistry_mapping,
                order=1,
                learning_objectives=[self.math_objective],
            )

    def test_subject_topic_and_entry_resources_with_metadata_and_provenance(self):
        prescribed = CurriculumResourceService.save_resource(
            curriculum_subject=self.math_subject,
            resource_type=CurriculumResourceType.PRESCRIBED_TEXT,
            title="Redemption Road",
            metadata={"category": "African Prose", "author": "Elma Shaw"},
            source=self.source,
            source_page_start=20,
            source_page_end=21,
            source_reference="WAEC 2026-2030",
            import_batch=self.batch,
        )
        entry = PublishedSchemeService.save_entry(
            published_scheme=self.scheme,
            term_number=1,
            week_start=1,
            curriculum_topic=self.chemistry_mapping,
            order=1,
        )
        note = CurriculumResourceService.save_resource(
            curriculum_subject=self.chemistry_subject,
            curriculum_topic=self.chemistry_mapping,
            resource_type=CurriculumResourceType.INSTRUCTIONAL_NOTE,
            title="History of Chemistry",
            content="Official extracted note.",
        )
        evaluation = CurriculumResourceService.save_resource(
            curriculum_subject=self.chemistry_subject,
            curriculum_topic=self.chemistry_mapping,
            published_scheme_entry=entry,
            resource_type=CurriculumResourceType.EVALUATION,
            title="Week 1 Evaluation",
        )
        self.assertEqual(prescribed.metadata["author"], "Elma Shaw")
        self.assertEqual(prescribed.source, self.source)
        self.assertEqual(prescribed.import_batch, self.batch)
        self.assertEqual(note.curriculum_topic, self.chemistry_mapping)
        self.assertEqual(evaluation.published_scheme_entry, entry)

    def test_resource_cross_subject_scopes_are_rejected(self):
        entry = PublishedSchemeService.save_entry(
            published_scheme=self.scheme, term_number=1, week_start=1, order=1
        )
        with self.assertRaises(ValidationError):
            CurriculumResourceService.save_resource(
                curriculum_subject=self.math_subject,
                curriculum_topic=self.chemistry_mapping,
                resource_type=CurriculumResourceType.OTHER,
                title="Wrong topic scope",
            )
        with self.assertRaises(ValidationError):
            CurriculumResourceService.save_resource(
                curriculum_subject=self.math_subject,
                published_scheme_entry=entry,
                resource_type=CurriculumResourceType.OTHER,
                title="Wrong entry scope",
            )

    def test_read_only_api_lists_filterable_foundation(self):
        CurriculumResourceService.save_resource(
            curriculum_subject=self.chemistry_subject,
            resource_type=CurriculumResourceType.REFERENCE,
            title="Chemistry Reference",
        )
        client = APIClient(HTTP_HOST=self.domain.domain)
        client.force_authenticate(self.user)
        response = client.get(
            reverse("published-scheme-list"),
            {"curriculum_subject": self.chemistry_subject.pk},
        )
        self.assertEqual(response.status_code, 200)
        response = client.get(
            reverse("curriculum-resource-list"),
            {"curriculum_subject": self.chemistry_subject.pk},
        )
        self.assertEqual(response.status_code, 200)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(client.post(reverse("published-scheme-list"), {}).status_code, 405)
