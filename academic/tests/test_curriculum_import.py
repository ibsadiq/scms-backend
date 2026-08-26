from school.testcases import TenantTestCase
from academic.models import (
    Curriculum,
    CurriculumSource,
    CurriculumImportBatch,
    ImportBatchStatus,
    SourceType,
    CurriculumSubject,
    GradeLevel,
    Subject,
    Topic,
    CurriculumTopic,
    SubTopic,
    LearningObjective,
    CurriculumGuidance,
    SchoolSection,
)
from academic.models.choices import CurriculumAuthority
from academic.services.curriculum_import_service import (
    CurriculumImportService,
    CurriculumImportError,
)
from tenants.models import TenantStatus
from users.models import CustomUser


class CurriculumImportServiceTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.admin = CustomUser.objects.create_user(
            email="admin@test.com", password="password123", is_admin=True
        )
        self.section = SchoolSection.objects.create(
            system_code="JSS", default_name="Junior Secondary", sequence_order=3
        )
        self.grade_jss1 = GradeLevel.objects.create(
            system_code="JSS_1", default_name="JSS 1", alias="Year 7", section="JSS", sequence_order=12
        )
        self.grade_jss2 = GradeLevel.objects.create(
            system_code="JSS_2", default_name="JSS 2", alias="Year 8", section="JSS", sequence_order=13
        )
        self.subject_math = Subject.objects.create(
            name="Mathematics", subject_code="MATH", is_selectable=False, graded=True
        )
        self.subject_eng = Subject.objects.create(
            name="English Language", subject_code="ENG", is_selectable=False, graded=True
        )
        self.curriculum = Curriculum.objects.create(
            name="Nigerian Basic Education Curriculum",
            version="2024",
            authority_type=CurriculumAuthority.NERDC,
            is_active=True,
        )
        self.curriculum_cambridge = Curriculum.objects.create(
            name="Cambridge Lower Secondary",
            version="2023",
            authority_type=CurriculumAuthority.OTHER,
            is_active=True,
        )
        self.cs_math_jss1 = CurriculumSubject.objects.create(
            curriculum=self.curriculum,
            subject=self.subject_math,
            grade_level=self.grade_jss1,
            is_active=True,
        )
        self.cs_eng_jss1 = CurriculumSubject.objects.create(
            curriculum=self.curriculum,
            subject=self.subject_eng,
            grade_level=self.grade_jss1,
            is_active=True,
        )

        self.sample_payload = {
            "curriculum": {
                "name": "Nigerian Basic Education Curriculum",
                "version": "2024",
            },
            "source": {
                "title": "NERDC JSS 1 Mathematics Manual",
                "authority": "NERDC",
                "publication_year": 2024,
                "version": "2024",
                "original_filename": "nerdc_math_jss1.pdf",
                "source_type": "PDF",
                "source_reference": "ISBN 978-978-000-111-2",
                "checksum_sha256": "1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff",
            },
            "grades": [
                {
                    "grade": "JSS_1",
                    "subjects": [
                        {
                            "subject": "Mathematics",
                            "topics": [
                                {
                                    "name": "Number Bases",
                                    "order": 1,
                                    "theme": "Number and Numeration",
                                    "content_summary": "Base 10 and Base 2 systems.",
                                    "_source": {
                                        "page_start": 10,
                                        "page_end": 12,
                                        "reference": "Module 1",
                                    },
                                    "subtopics": [
                                        "Decimal Number Base",
                                        "Binary Number Base",
                                    ],
                                    "learning_objectives": [
                                        {
                                            "order": 1,
                                            "description": "Identify place values.",
                                            "subtopic": "Decimal Number Base",
                                            "_source": {
                                                "page": 10,
                                                "reference": "Obj 1.1",
                                            },
                                        },
                                        {
                                            "order": 2,
                                            "description": "Convert binary to base ten.",
                                            "subtopic": "Binary Number Base",
                                            "_source": {
                                                "page": 11,
                                                "reference": "Obj 1.2",
                                            },
                                        },
                                    ],
                                    "guidance": {
                                        "teacher_activities": "Demonstrate counting.",
                                        "learner_activities": "Group counters.",
                                        "teaching_learning_materials": "Abacus.",
                                        "evaluation_guide": "Convert 1101 to base ten.",
                                        "notes": "NERDC Junior Secondary Mathematics curriculum, p. 10.",
                                    },
                                },
                                {
                                    "name": "Fractions",
                                    "order": 2,
                                    "theme": "Number and Numeration",
                                    "content_summary": "Basic operations on fractions.",
                                    "_source": {
                                        "page_start": 13,
                                        "page_end": 15,
                                        "reference": "Module 2",
                                    },
                                    "subtopics": [
                                        "Addition of Fractions",
                                    ],
                                    "learning_objectives": [
                                        {
                                            "order": 1,
                                            "description": "Add fractions with unlike denominators.",
                                            "subtopic": "Addition of Fractions",
                                            "_source": {
                                                "page": 13,
                                                "reference": "Obj 2.1",
                                            },
                                        }
                                    ],
                                    "guidance": {
                                        "teacher_activities": "Use fraction cutouts.",
                                        "learner_activities": "Fold paper strips.",
                                        "teaching_learning_materials": "Paper strips.",
                                        "evaluation_guide": "Solve 1/2 + 1/3.",
                                        "notes": "NERDC p. 12.",
                                    },
                                },
                            ],
                        }
                    ],
                }
            ],
        }

    def test_01_valid_clean_import_with_provenance(self):
        """1. Clean import creates CurriculumSource, CurriculumImportBatch, and links provenance."""
        metrics, source_obj, batch_obj = CurriculumImportService.import_content(
            data=self.sample_payload,
            curriculum=self.curriculum,
            imported_by=self.admin,
        )
        self.assertEqual(metrics.counts["CurriculumSource"]["CREATED"], 1)
        self.assertEqual(metrics.counts["Topic"]["CREATED"], 2)
        self.assertEqual(metrics.counts["CurriculumTopic"]["CREATED"], 2)
        self.assertEqual(metrics.counts["SubTopic"]["CREATED"], 3)
        self.assertEqual(metrics.counts["LearningObjective"]["CREATED"], 3)
        self.assertEqual(metrics.counts["CurriculumGuidance"]["CREATED"], 2)

        # Verify Source
        self.assertIsNotNone(source_obj)
        self.assertEqual(source_obj.title, "NERDC JSS 1 Mathematics Manual")
        self.assertEqual(source_obj.checksum_sha256, "1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff")

        # Verify Batch
        self.assertIsNotNone(batch_obj)
        self.assertEqual(batch_obj.status, ImportBatchStatus.COMPLETED)
        self.assertEqual(batch_obj.source, source_obj)
        self.assertEqual(batch_obj.imported_by, self.admin)
        self.assertEqual(batch_obj.summary["Topic"]["CREATED"], 2)

        # Verify CurriculumTopic Provenance
        ct_bases = CurriculumTopic.objects.get(topic__name="Number Bases")
        self.assertEqual(ct_bases.source, source_obj)
        self.assertEqual(ct_bases.source_page_start, 10)
        self.assertEqual(ct_bases.source_page_end, 12)
        self.assertEqual(ct_bases.source_reference, "Module 1")
        self.assertEqual(ct_bases.last_import_batch, batch_obj)

        # Verify LearningObjective Provenance
        lo1 = ct_bases.learning_objectives.get(order=1)
        self.assertEqual(lo1.source_page, 10)
        self.assertEqual(lo1.source_reference, "Obj 1.1")
        self.assertEqual(lo1.last_import_batch, batch_obj)

    def test_02_source_sha256_normalization(self):
        """2. Checksum is normalized to lowercase."""
        payload = dict(self.sample_payload)
        payload["source"]["checksum_sha256"] = "1111222233334444555566667777888899990000AAAABBBBCCCCDDDDEEEEFFFF"

        metrics, source_obj, batch_obj = CurriculumImportService.import_content(
            data=payload,
            curriculum=self.curriculum,
        )
        self.assertEqual(source_obj.checksum_sha256, "1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff")

    def test_03_invalid_checksum_rejection(self):
        """3. Invalid checksum length or non-hex string raises error."""
        payload = dict(self.sample_payload)
        payload["source"]["checksum_sha256"] = "too_short_hash"

        with self.assertRaises(CurriculumImportError) as ctx:
            CurriculumImportService.import_content(data=payload, curriculum=self.curriculum)
        self.assertTrue(any("64 hexadecimal characters" in e for e in ctx.exception.errors))

    def test_04_same_curriculum_and_checksum_reuse(self):
        """4. Uploading same source with same checksum reuses existing CurriculumSource."""
        CurriculumImportService.import_content(
            data=self.sample_payload,
            curriculum=self.curriculum,
        )
        self.assertEqual(CurriculumSource.objects.count(), 1)

        # Second import
        metrics2, source2, batch2 = CurriculumImportService.import_content(
            data=self.sample_payload,
            curriculum=self.curriculum,
        )
        self.assertEqual(metrics2.counts["CurriculumSource"]["REUSED"], 1)
        self.assertEqual(metrics2.counts["CurriculumSource"]["CREATED"], 0)
        self.assertEqual(CurriculumSource.objects.count(), 1)

    def test_05_same_filename_different_checksum_does_not_merge(self):
        """5. Same filename with different checksum creates distinct CurriculumSource."""
        CurriculumImportService.import_content(
            data=self.sample_payload,
            curriculum=self.curriculum,
        )
        self.assertEqual(CurriculumSource.objects.count(), 1)

        # Different checksum payload
        payload2 = dict(self.sample_payload)
        payload2["source"] = dict(self.sample_payload["source"])
        payload2["source"]["checksum_sha256"] = "9999888877776666555544443333222211110000ffffeeeeddddccccbbbbaaaa"

        metrics2, source2, batch2 = CurriculumImportService.import_content(
            data=payload2,
            curriculum=self.curriculum,
        )
        self.assertEqual(CurriculumSource.objects.count(), 2)

    def test_08_source_with_no_checksum_allowed(self):
        """8. Source without checksum is allowed and does not raise constraint violation."""
        payload = dict(self.sample_payload)
        payload["source"] = {
            "title": "Draft Syllabus Notes",
            "authority": "School Internal",
        }
        metrics, source_obj, batch_obj = CurriculumImportService.import_content(
            data=payload,
            curriculum=self.curriculum,
        )
        self.assertIsNotNone(source_obj)
        self.assertEqual(source_obj.checksum_sha256, "")
        self.assertEqual(CurriculumSource.objects.count(), 1)

    def test_09_cross_curriculum_source_rejection(self):
        """9. Passing a source belonging to Curriculum A to Curriculum B is rejected."""
        source_cambridge = CurriculumSource.objects.create(
            curriculum=self.curriculum_cambridge,
            title="Cambridge Math Guide",
        )
        with self.assertRaises(CurriculumImportError) as ctx:
            CurriculumImportService.import_content(
                data=self.sample_payload,
                curriculum=self.curriculum,
                source=source_cambridge,
            )
        self.assertTrue(any("does not match target curriculum" in e for e in ctx.exception.errors))

    def test_13_dry_run_does_not_persist_batch_or_source(self):
        """13. Dry run executes save path but leaves 0 batch and 0 source records."""
        metrics, source_obj, batch_obj = CurriculumImportService.import_content(
            data=self.sample_payload,
            curriculum=self.curriculum,
            dry_run=True,
        )
        self.assertEqual(CurriculumSource.objects.count(), 0)
        self.assertEqual(CurriculumImportBatch.objects.count(), 0)
        self.assertEqual(Topic.objects.count(), 0)
        self.assertEqual(CurriculumTopic.objects.count(), 0)

    def test_15_topic_page_range_validation(self):
        """15. Invalid topic page range (page_end < page_start) triggers validation error."""
        bad_payload = dict(self.sample_payload)
        bad_payload["grades"][0]["subjects"][0]["topics"][0]["_source"] = {
            "page_start": 20,
            "page_end": 10,
        }
        with self.assertRaises(CurriculumImportError) as ctx:
            CurriculumImportService.import_content(data=bad_payload, curriculum=self.curriculum)
        self.assertTrue(any("cannot be less than 'page_start'" in e for e in ctx.exception.errors))

    def test_17_objective_page_validation(self):
        """17. Non-positive objective page triggers validation error."""
        bad_payload = dict(self.sample_payload)
        bad_payload["grades"][0]["subjects"][0]["topics"][0]["learning_objectives"][0]["_source"] = {
            "page": 0,
        }
        with self.assertRaises(CurriculumImportError) as ctx:
            CurriculumImportService.import_content(data=bad_payload, curriculum=self.curriculum)
        self.assertTrue(any("must be a positive integer" in e for e in ctx.exception.errors))

    def test_18_legacy_json_without_source_still_works(self):
        """18 & 19. Legacy JSON payload without source metadata imports cleanly without error."""
        legacy_payload = {
            "curriculum": {"name": "Nigerian Basic Education Curriculum", "version": "2024"},
            "grades": [
                {
                    "grade": "JSS_1",
                    "subjects": [
                        {
                            "subject": "Mathematics",
                            "topics": [
                                {"name": "Geometry Basics", "order": 1}
                            ]
                        }
                    ]
                }
            ]
        }
        metrics, source_obj, batch_obj = CurriculumImportService.import_content(
            data=legacy_payload,
            curriculum=self.curriculum,
        )
        self.assertIsNone(source_obj)
        self.assertIsNotNone(batch_obj)
        self.assertEqual(Topic.objects.count(), 1)
        ct = CurriculumTopic.objects.first()
        self.assertIsNone(ct.source)
        self.assertEqual(ct.last_import_batch, batch_obj)

    def test_20_idempotent_provenance_rerun_and_22_no_last_import_batch_advance(self):
        """20 & 22. Re-importing identical content does not update records or advance last_import_batch."""
        # Batch 1
        metrics1, src1, batch1 = CurriculumImportService.import_content(
            data=self.sample_payload,
            curriculum=self.curriculum,
        )
        ct = CurriculumTopic.objects.get(topic__name="Number Bases")
        lo = ct.learning_objectives.get(order=1)
        self.assertEqual(ct.last_import_batch, batch1)
        self.assertEqual(lo.last_import_batch, batch1)

        # Batch 2 (identical rerun)
        metrics2, src2, batch2 = CurriculumImportService.import_content(
            data=self.sample_payload,
            curriculum=self.curriculum,
        )
        self.assertEqual(metrics2.counts["CurriculumTopic"]["UNCHANGED"], 2)
        self.assertEqual(metrics2.counts["LearningObjective"]["UNCHANGED"], 3)

        # Verify last_import_batch DID NOT advance to batch2 for unchanged records!
        ct.refresh_from_db()
        lo.refresh_from_db()
        self.assertEqual(ct.last_import_batch, batch1)
        self.assertEqual(lo.last_import_batch, batch1)

    def test_21_provenance_change_counts_as_updated_and_advances_batch(self):
        """21. Updating page citation on existing topic counts as UPDATED and assigns new batch."""
        metrics1, src1, batch1 = CurriculumImportService.import_content(
            data=self.sample_payload,
            curriculum=self.curriculum,
        )
        ct = CurriculumTopic.objects.get(topic__name="Number Bases")
        self.assertEqual(ct.source_page_start, 10)
        self.assertEqual(ct.last_import_batch, batch1)

        # Modified page citation in payload
        modified = dict(self.sample_payload)
        modified["grades"][0]["subjects"][0]["topics"][0]["_source"] = {
            "page_start": 25,
            "page_end": 28,
            "reference": "Module 1 Revision",
        }

        metrics2, src2, batch2 = CurriculumImportService.import_content(
            data=modified,
            curriculum=self.curriculum,
        )
        self.assertEqual(metrics2.counts["CurriculumTopic"]["UPDATED"], 1)

        ct.refresh_from_db()
        self.assertEqual(ct.source_page_start, 25)
        self.assertEqual(ct.source_page_end, 28)
        self.assertEqual(ct.last_import_batch, batch2)

    def test_23_no_provenance_on_topic_and_24_no_provenance_on_subtopic(self):
        """23 & 24. Topic and SubTopic models do not have source or batch fields."""
        topic = Topic.objects.create(
            grade_level=self.grade_jss1,
            subject=self.subject_math,
            name="Arithmetic",
        )
        subtopic = SubTopic.objects.create(
            topic=topic,
            name="Addition",
        )
        self.assertFalse(hasattr(topic, "source"))
        self.assertFalse(hasattr(topic, "last_import_batch"))
        self.assertFalse(hasattr(subtopic, "source"))
        self.assertFalse(hasattr(subtopic, "last_import_batch"))

    def test_25_omitted_source_does_not_erase_existing_provenance(self):
        """25. Subsequent import without _source does not erase existing source citations."""
        CurriculumImportService.import_content(
            data=self.sample_payload,
            curriculum=self.curriculum,
        )
        ct = CurriculumTopic.objects.get(topic__name="Number Bases")
        self.assertEqual(ct.source_page_start, 10)
        self.assertIsNotNone(ct.source)

        # Import update with no source block
        update_payload = {
            "curriculum": {"name": "Nigerian Basic Education Curriculum", "version": "2024"},
            "grades": [
                {
                    "grade": "JSS_1",
                    "subjects": [
                        {
                            "subject": "Mathematics",
                            "topics": [
                                {
                                    "name": "Number Bases",
                                    "order": 1,
                                    "theme": "Advanced Numeration",
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        metrics, src, batch = CurriculumImportService.import_content(
            data=update_payload,
            curriculum=self.curriculum,
        )
        ct.refresh_from_db()
        self.assertEqual(ct.theme, "Advanced Numeration")
        # Existing source was preserved
        self.assertIsNotNone(ct.source)
