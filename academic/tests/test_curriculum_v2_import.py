"""Tests for Canonical Curriculum JSON V2 import pipeline.

Covers:
  - topic_key identity and theme separation
  - repeated topic placement (same topic, multiple scheme entries)
  - week range entries
  - non-instructional entries (BREAK, EXAMINATION)
  - teacher/pupil activities on entries
  - prescribed-text resources (no topic/entry scope)
  - scoped resources with topic_ref and published_scheme_entry_ref
  - idempotency (import same payload twice → no duplicate records)
  - dry-run (no DB records created)
  - V2 validator rejections (theme-is-term, unresolved topic_ref, entry_key collision)
"""
from school.testcases import TenantTestCase
from academic.models import (
    Curriculum,
    CurriculumResource,
    CurriculumSubject,
    CurriculumTopic,
    GradeLevel,
    LearningObjective,
    PublishedScheme,
    PublishedSchemeEntry,
    PublishedSchemeEntryType,
    SchoolSection,
    Subject,
    SubTopic,
    Topic,
)
from academic.models.choices import CurriculumAuthority
from academic.services.curriculum_import_service import (
    CurriculumImportError,
    CurriculumImportService,
)
from academic.services.curriculum_v2_validator import validate_v2


# ---------------------------------------------------------------------------
# Shared fixture builders
# ---------------------------------------------------------------------------

def _minimal_v2(**kwargs) -> dict:
    """Build a minimal valid V2 payload."""
    base = {
        "schema_version": "2.0",
        "curriculum": {"name": "NERDC 2025 Test", "version": "2025"},
        "source": {"title": "Test Source 2025"},
        "grades": [],
    }
    base.update(kwargs)
    return base


def _grade_subject(grade: str, subject: str, topics=None, schemes=None, resources=None) -> dict:
    return {
        "grade": grade,
        "subjects": [{
            "subject": subject,
            "topics": topics or [],
            "published_schemes": schemes or [],
            "resources": resources or [],
        }],
    }


def _topic(name: str, topic_key: str, theme: str = "", subtopics=None, objectives=None, order: int = 1) -> dict:
    return {
        "name": name,
        "topic_key": topic_key,
        "theme": theme,
        "order": order,
        "content_summary": "",
        "subtopics": subtopics or [],
        "learning_objectives": objectives or [],
        "guidance": None,
    }


def _scheme(entries=None, name="Published Scheme of Work", version="2025") -> dict:
    return {
        "name": name,
        "version": version,
        "entries": entries or [],
    }


def _entry(
    entry_key: str,
    term: int,
    week_start,
    topic_ref=None,
    title: str = "",
    order: int = 1,
    entry_type: str = "INSTRUCTION",
    week_end=None,
    subtopic_refs=None,
    lo_refs=None,
    teacher_activities: str = "",
    pupil_activities: str = "",
    learning_resources: str = "",
) -> dict:
    return {
        "entry_key": entry_key,
        "term_number": term,
        "week_start": week_start,
        "week_end": week_end,
        "entry_type": entry_type,
        "topic_ref": topic_ref,
        "title": title or topic_ref or "",
        "order": order,
        "content_summary": "",
        "subtopic_refs": subtopic_refs or [],
        "learning_objective_refs": lo_refs or [],
        "teacher_activities": teacher_activities,
        "pupil_activities": pupil_activities,
        "learning_resources": learning_resources,
    }


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class CurriculumV2ImportTests(TenantTestCase):

    def setUp(self):
        super().setUp()

        # School section
        self.section_ss = SchoolSection.objects.create(
            system_code="SS", default_name="Senior Secondary", sequence_order=5
        )

        # Grades
        self.grade_ss1 = GradeLevel.objects.create(
            system_code="SS_1", default_name="SS 1", alias="SSS1",
            section="SS", sequence_order=25,
        )

        # Subjects
        self.subj_math = Subject.objects.create(
            name="Mathematics", subject_code="MATH_V2", is_selectable=False, graded=True
        )
        self.subj_chem = Subject.objects.create(
            name="Chemistry", subject_code="CHEM_V2", is_selectable=False, graded=True
        )
        self.subj_eng = Subject.objects.create(
            name="English Language", subject_code="ENGV2", is_selectable=False, graded=True
        )

        # Curriculum
        self.curriculum = Curriculum.objects.create(
            name="NERDC 2025 Test",
            version="2025",
            authority_type=CurriculumAuthority.NERDC,
            is_active=True,
        )

        # CurriculumSubject mappings
        self.cs_math = CurriculumSubject.objects.create(
            curriculum=self.curriculum,
            subject=self.subj_math,
            grade_level=self.grade_ss1,
        )
        self.cs_chem = CurriculumSubject.objects.create(
            curriculum=self.curriculum,
            subject=self.subj_chem,
            grade_level=self.grade_ss1,
        )
        self.cs_eng = CurriculumSubject.objects.create(
            curriculum=self.curriculum,
            subject=self.subj_eng,
            grade_level=self.grade_ss1,
        )

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _import(self, payload: dict, dry_run: bool = False) -> tuple:
        return CurriculumImportService.import_content(
            data=payload,
            curriculum=self.curriculum,
            dry_run=dry_run,
        )

    # ── Test 1: topic_key identity & theme ───────────────────────────────────

    def test_v2_ss1_math_theme_and_topic_identity(self):
        """topic_key used for identity; theme stored on CurriculumTopic, not mangled."""
        payload = _minimal_v2(grades=[_grade_subject(
            "SS_1", "Mathematics",
            topics=[_topic(
                "Number Base System",
                topic_key="number-base-system",
                theme="Number and Numeration",
                subtopics=[
                    {"name": "Conversion from one base to base 10", "order": 1},
                    {"name": "Arithmetic operations in number bases", "order": 2},
                    {"name": "Application to computer programming", "order": 3},
                ],
            )],
        )])

        metrics, source_obj, batch_obj = self._import(payload)

        # One Topic
        self.assertEqual(Topic.objects.count(), 1)
        topic = Topic.objects.get()
        self.assertEqual(topic.name, "Number Base System")

        # One CurriculumTopic with theme (not a term)
        self.assertEqual(CurriculumTopic.objects.count(), 1)
        ct = CurriculumTopic.objects.get()
        self.assertEqual(ct.theme, "Number and Numeration")

        # Three SubTopics
        self.assertEqual(SubTopic.objects.filter(topic=topic).count(), 3)

        # Metrics
        self.assertEqual(metrics.counts["Topic"]["CREATED"], 1)
        self.assertEqual(metrics.counts["CurriculumTopic"]["CREATED"], 1)
        self.assertEqual(metrics.counts["SubTopic"]["CREATED"], 3)

    # ── Test 2: repeated topic placement ────────────────────────────────────

    def test_v2_repeated_topic_placement(self):
        """Same topic referenced in two different scheme entries → 1 CurriculumTopic, 2 entries."""
        payload = _minimal_v2(grades=[_grade_subject(
            "SS_1", "Mathematics",
            topics=[_topic("Fractions", topic_key="fractions", theme="Number and Numeration")],
            schemes=[_scheme(entries=[
                _entry("term-1-week-3-fractions", term=1, week_start=3, topic_ref="fractions", order=1),
                _entry("term-2-week-6-fractions", term=2, week_start=6, topic_ref="fractions", order=1),
            ])],
        )])

        self._import(payload)

        # 1 Topic, 1 CurriculumTopic
        self.assertEqual(Topic.objects.count(), 1)
        self.assertEqual(CurriculumTopic.objects.count(), 1)

        # 1 PublishedScheme, 2 PublishedSchemeEntries
        self.assertEqual(PublishedScheme.objects.count(), 1)
        self.assertEqual(PublishedSchemeEntry.objects.count(), 2)

        ct = CurriculumTopic.objects.get()
        entries = PublishedSchemeEntry.objects.order_by("term_number")
        self.assertEqual(entries[0].term_number, 1)
        self.assertEqual(entries[0].week_start, 3)
        self.assertEqual(entries[1].term_number, 2)
        self.assertEqual(entries[1].week_start, 6)
        self.assertEqual(entries[0].curriculum_topic, ct)
        self.assertEqual(entries[1].curriculum_topic, ct)

    # ── Test 3: week range entry ─────────────────────────────────────────────

    def test_v2_week_range(self):
        """Entry with week_start + week_end and PREPARATION type (no topic)."""
        payload = _minimal_v2(grades=[_grade_subject(
            "SS_1", "Mathematics",
            topics=[],
            schemes=[_scheme(entries=[
                _entry(
                    "term-1-week-7-10-prep",
                    term=1, week_start=7, week_end=10,
                    entry_type="PREPARATION",
                    topic_ref=None,
                    title="Preparation Period",
                    order=1,
                ),
            ])],
        )])

        self._import(payload)

        self.assertEqual(PublishedSchemeEntry.objects.count(), 1)
        entry = PublishedSchemeEntry.objects.get()
        self.assertEqual(entry.week_start, 7)
        self.assertEqual(entry.week_end, 10)
        self.assertEqual(entry.entry_type, PublishedSchemeEntryType.PREPARATION)
        self.assertIsNone(entry.curriculum_topic)

    # ── Test 4: non-instructional BREAK ──────────────────────────────────────

    def test_v2_non_instructional_no_topic(self):
        """BREAK entry with no topic_ref or week creates an entry with null curriculum_topic."""
        payload = _minimal_v2(grades=[_grade_subject(
            "SS_1", "Mathematics",
            schemes=[_scheme(entries=[
                _entry(
                    "term-1-midterm-break",
                    term=1, week_start=None,
                    entry_type="BREAK",
                    topic_ref=None,
                    title="Midterm Break",
                    order=8,
                ),
            ])],
        )])

        self._import(payload)

        self.assertEqual(Topic.objects.count(), 0)
        self.assertEqual(PublishedSchemeEntry.objects.count(), 1)
        entry = PublishedSchemeEntry.objects.get()
        self.assertIsNone(entry.curriculum_topic)
        self.assertEqual(entry.entry_type, PublishedSchemeEntryType.BREAK)
        self.assertIsNone(entry.week_start)

    # ── Test 5: teacher/pupil activities on entry ────────────────────────────

    def test_v2_activities_on_entry(self):
        """teacher_activities and pupil_activities are stored on PublishedSchemeEntry."""
        payload = _minimal_v2(grades=[_grade_subject(
            "SS_1", "Mathematics",
            topics=[_topic("Introduction to Sets", topic_key="introduction-to-sets")],
            schemes=[_scheme(entries=[
                _entry(
                    "term-1-week-1-sets",
                    term=1, week_start=1,
                    topic_ref="introduction-to-sets",
                    order=1,
                    teacher_activities="Explain concept of sets with examples.",
                    pupil_activities="Solve set problems in pairs.",
                    learning_resources="Textbook Chapter 1",
                ),
            ])],
        )])

        self._import(payload)

        entry = PublishedSchemeEntry.objects.get()
        self.assertEqual(entry.teacher_activities, "Explain concept of sets with examples.")
        self.assertEqual(entry.pupil_activities, "Solve set problems in pairs.")
        self.assertEqual(entry.learning_resources, "Textbook Chapter 1")

    # ── Test 6: prescribed-text resource (no topic / entry scope) ───────────

    def test_v2_literature_prescribed_texts(self):
        """PRESCRIBED_TEXT resources at subject level (no topic_ref, no entry_ref)."""
        payload = _minimal_v2(grades=[_grade_subject(
            "SS_1", "English Language",
            resources=[
                {
                    "resource_type": "PRESCRIBED_TEXT",
                    "title": "Redemption Road",
                    "content": "",
                    "topic_ref": None,
                    "published_scheme_entry_ref": None,
                    "order": 1,
                    "metadata": {
                        "category": "African Prose",
                        "author": "Elma Shaw",
                        "authority": "WAEC",
                        "examination": "WASSCE",
                    },
                },
                {
                    "resource_type": "PRESCRIBED_TEXT",
                    "title": "The Gods Are Not to Blame",
                    "content": "",
                    "topic_ref": None,
                    "published_scheme_entry_ref": None,
                    "order": 2,
                    "metadata": {
                        "category": "Drama",
                        "author": "Ola Rotimi",
                        "authority": "WAEC",
                        "examination": "WASSCE",
                    },
                },
            ],
        )])

        self._import(payload)

        resources = CurriculumResource.objects.all()
        self.assertEqual(resources.count(), 2)
        for r in resources:
            self.assertIsNone(r.curriculum_topic)
            self.assertIsNone(r.published_scheme_entry)
            self.assertEqual(r.resource_type, "PRESCRIBED_TEXT")

        titles = {r.title for r in resources}
        self.assertIn("Redemption Road", titles)
        self.assertIn("The Gods Are Not to Blame", titles)

    # ── Test 7: scoped resources (topic_ref + entry_ref) ────────────────────

    def test_v2_scoped_resources(self):
        """Resources with topic_ref and published_scheme_entry_ref are linked correctly."""
        payload = _minimal_v2(grades=[_grade_subject(
            "SS_1", "Chemistry",
            topics=[_topic("Introduction to Chemistry", topic_key="introduction-to-chemistry")],
            schemes=[_scheme(entries=[
                _entry(
                    "term-1-week-1-intro-chem",
                    term=1, week_start=1,
                    topic_ref="introduction-to-chemistry",
                    title="Introduction to Chemistry",
                    order=1,
                ),
            ])],
            resources=[
                {
                    "resource_type": "INSTRUCTIONAL_NOTE",
                    "title": "History of Chemistry",
                    "content": "Chemistry has ancient roots...",
                    "topic_ref": "introduction-to-chemistry",
                    "published_scheme_entry_ref": "term-1-week-1-intro-chem",
                    "order": 1,
                    "metadata": {},
                },
                {
                    "resource_type": "EVALUATION",
                    "title": "Chemistry Entry Quiz",
                    "content": "",
                    "topic_ref": "introduction-to-chemistry",
                    "published_scheme_entry_ref": "term-1-week-1-intro-chem",
                    "order": 2,
                    "metadata": {},
                },
            ],
        )])

        self._import(payload)

        ct = CurriculumTopic.objects.get()
        entry = PublishedSchemeEntry.objects.get()
        resources = CurriculumResource.objects.order_by("order")
        self.assertEqual(resources.count(), 2)
        for r in resources:
            self.assertEqual(r.curriculum_topic, ct)
            self.assertEqual(r.published_scheme_entry, entry)

    # ── Test 8: idempotency ──────────────────────────────────────────────────

    def test_v2_idempotency(self):
        """Importing the same V2 payload twice does not create duplicate records."""
        payload = _minimal_v2(grades=[_grade_subject(
            "SS_1", "Mathematics",
            topics=[
                _topic("Sets", topic_key="sets", theme="Algebra", subtopics=[
                    {"name": "Definition of sets", "order": 1},
                    {"name": "Types of sets", "order": 2},
                ]),
            ],
            schemes=[_scheme(entries=[
                _entry("term-1-week-1-sets", term=1, week_start=1, topic_ref="sets", order=1),
            ])],
            resources=[
                {
                    "resource_type": "REFERENCE",
                    "title": "New General Mathematics SS1",
                    "content": "",
                    "topic_ref": "sets",
                    "published_scheme_entry_ref": "term-1-week-1-sets",
                    "order": 1,
                    "metadata": {},
                },
            ],
        )])

        self._import(payload)
        self._import(payload)  # second import

        self.assertEqual(Topic.objects.count(), 1)
        self.assertEqual(CurriculumTopic.objects.count(), 1)
        self.assertEqual(SubTopic.objects.count(), 2)
        self.assertEqual(PublishedScheme.objects.count(), 1)
        self.assertEqual(PublishedSchemeEntry.objects.count(), 1)
        self.assertEqual(CurriculumResource.objects.count(), 1)

    # ── Test 9: dry-run ──────────────────────────────────────────────────────

    def test_v2_dry_run(self):
        """Dry-run mode: validation passes but no DB records are created."""
        payload = _minimal_v2(grades=[_grade_subject(
            "SS_1", "Mathematics",
            topics=[_topic("Calculus", topic_key="calculus", theme="Calculus")],
            schemes=[_scheme(entries=[
                _entry("term-3-week-1-calculus", term=3, week_start=1, topic_ref="calculus", order=1),
            ])],
        )])

        metrics, source_obj, batch_obj = self._import(payload, dry_run=True)

        # Nothing persisted
        self.assertEqual(Topic.objects.count(), 0)
        self.assertEqual(CurriculumTopic.objects.count(), 0)
        self.assertEqual(PublishedScheme.objects.count(), 0)
        self.assertEqual(PublishedSchemeEntry.objects.count(), 0)

        # But metrics were computed (actions planned)
        self.assertGreater(metrics.total("CREATED"), 0)

    # ── Test 10: validator rejects theme-is-term ─────────────────────────────

    def test_v2_validator_rejects_term_as_theme(self):
        """validate_v2() produces ERROR when theme looks like a term label."""
        data = _minimal_v2(grades=[_grade_subject(
            "SS_1", "Mathematics",
            topics=[_topic("Fractions", topic_key="fractions", theme="First Term")],
        )])

        report = validate_v2(data)
        codes = {i.code for i in report.get_errors()}
        self.assertIn("THEME_IS_TERM", codes)

    # ── Test 11: validator rejects unresolved topic_ref ──────────────────────

    def test_v2_validator_rejects_unresolved_topic_ref(self):
        """validate_v2() produces ERROR when topic_ref doesn't match any topic_key."""
        data = _minimal_v2(grades=[_grade_subject(
            "SS_1", "Mathematics",
            topics=[_topic("Fractions", topic_key="fractions")],
            schemes=[_scheme(entries=[
                _entry("term-1-week-1-nonexistent", term=1, week_start=1,
                       topic_ref="nonexistent-topic", order=1),
            ])],
        )])

        report = validate_v2(data)
        codes = {i.code for i in report.get_errors()}
        self.assertIn("UNRESOLVED_TOPIC_REF", codes)

    # ── Test 12: validator rejects duplicate entry_key ───────────────────────

    def test_v2_validator_rejects_duplicate_entry_key(self):
        """validate_v2() produces ERROR when two entries share the same entry_key."""
        data = _minimal_v2(grades=[_grade_subject(
            "SS_1", "Mathematics",
            topics=[_topic("Fractions", topic_key="fractions")],
            schemes=[_scheme(entries=[
                _entry("term-1-week-1-fractions", term=1, week_start=1, topic_ref="fractions", order=1),
                _entry("term-1-week-1-fractions", term=1, week_start=2, topic_ref="fractions", order=2),
            ])],
        )])

        report = validate_v2(data)
        codes = {i.code for i in report.get_errors()}
        self.assertIn("DUPLICATE_ENTRY_KEY", codes)

    # ── Test 13: subtopic_refs resolution ────────────────────────────────────

    def test_v2_subtopic_refs_on_entries(self):
        """Scheme entry subtopic_refs link to the correct SubTopic objects."""
        payload = _minimal_v2(grades=[_grade_subject(
            "SS_1", "Mathematics",
            topics=[_topic(
                "Indices", topic_key="indices",
                subtopics=[
                    {"name": "Laws of indices", "order": 1},
                    {"name": "Negative indices", "order": 2},
                ],
            )],
            schemes=[_scheme(entries=[
                _entry(
                    "term-1-week-2-indices",
                    term=1, week_start=2,
                    topic_ref="indices",
                    order=1,
                    subtopic_refs=["Laws of indices", "Negative indices"],
                ),
            ])],
        )])

        self._import(payload)

        entry = PublishedSchemeEntry.objects.get()
        subtopics = list(entry.subtopics.all())
        self.assertEqual(len(subtopics), 2)
        names = {s.name for s in subtopics}
        self.assertIn("Laws of indices", names)
        self.assertIn("Negative indices", names)

    # ── Test 14: make_topic_key helper ──────────────────────────────────────

    def test_make_topic_key(self):
        cases = [
            ("Number Base System", "number-base-system"),
            ("HCF (Highest Common Factor)", "hcf-highest-common-factor"),
            ("Fractions", "fractions"),
            ("Introduction to Chemistry", "introduction-to-chemistry"),
        ]
        for name, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(CurriculumImportService.make_topic_key(name), expected)

    # ── Test 15: V1 subtopic strings normalised internally ──────────────────

    def test_v1_subtopics_normalised_to_v2_form(self):
        """_normalize_subtopics_to_v2 handles both string and object forms."""
        result = CurriculumImportService._normalize_subtopics_to_v2([
            "Lesson one",
            {"name": "Lesson two", "order": 5},
            "Lesson three",
        ])
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["name"], "Lesson one")
        self.assertEqual(result[0]["order"], 1)
        self.assertEqual(result[1]["name"], "Lesson two")
        self.assertEqual(result[1]["order"], 5)
        self.assertEqual(result[2]["order"], 3)

    # ── Test 16: V1 payload still works ─────────────────────────────────────

    def test_v1_payload_still_works(self):
        """V1-style payloads (no schema_version) continue to import correctly via V1 path."""
        from academic.models import SchoolSection as _SS
        # We need a JSS section and grade for V1 test
        _SS.objects.get_or_create(
            system_code="JSS", defaults={"default_name": "Junior Secondary", "sequence_order": 3}
        )
        grade_jss1, _ = GradeLevel.objects.get_or_create(
            system_code="JSS_1",
            defaults={"default_name": "JSS 1", "alias": "Year 7", "section": "JSS", "sequence_order": 12},
        )
        subj_math_v1, _ = Subject.objects.get_or_create(
            subject_code="MATH_V1",
            defaults={"name": "Mathematics V1", "is_selectable": False, "graded": True},
        )
        curric_v1 = Curriculum.objects.create(
            name="Test V1 Curriculum",
            version="2024",
            authority_type=CurriculumAuthority.NERDC,
            is_active=True,
        )
        CurriculumSubject.objects.create(
            curriculum=curric_v1, subject=subj_math_v1, grade_level=grade_jss1
        )

        v1_payload = {
            # No schema_version — V1
            "curriculum": {"name": "Test V1 Curriculum", "version": "2024"},
            "source": {"title": "V1 Source"},
            "grades": [{
                "grade": "JSS_1",
                "subjects": [{
                    "subject": "Mathematics V1",
                    "topics": [{
                        "name": "Whole Numbers",
                        "order": 1,
                        "theme": "First Term",
                        "content_summary": "",
                        "subtopics": ["Definition", "Properties"],
                        "learning_objectives": [],
                    }],
                }],
            }],
        }

        metrics, *_ = CurriculumImportService.import_content(
            data=v1_payload,
            curriculum=curric_v1,
        )
        self.assertEqual(Topic.objects.filter(name="Whole Numbers").count(), 1)
        self.assertEqual(metrics.counts["Topic"]["CREATED"], 1)
