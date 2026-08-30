from django.core.exceptions import PermissionDenied
from django.db.models.deletion import ProtectedError

from school.testcases import TenantTestCase
from tenants.models import TenantStatus
from academic.models import (
    AllocatedSubject,
    ClassRoom,
    Curriculum,
    CurriculumSubject,
    CurriculumTopic,
    GradeLevel,
    LearningObjective,
    LessonPlan,
    PublishedScheme,
    PublishedSchemeEntry,
    PublishedSchemeEntryType,
    SchemeOfWorkStatus,
    SchoolSection,
    Subject,
    SubTopic,
    Teacher,
    Topic,
)
from academic.services.published_scheme_adoption_service import PublishedSchemeAdoptionService
from academic.services.curriculum_import_service import CurriculumImportService
from administration.models import AcademicYear, Term
from users.models import CustomUser


class CurriculumSubjectDecouplingTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        super().setup_tenant(tenant)
        tenant.status = TenantStatus.ACTIVE

    def setUp(self):
        super().setUp()
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-07-31",
            active_year=True,
        )
        self.term1 = Term.objects.create(
            academic_year=self.year,
            name="Term 1",
            start_date="2025-09-01",
            end_date="2025-12-15",
        )

        self.grade10 = GradeLevel.objects.create(
            system_code="SS_1",
            default_name="SS 1",
            sequence_order=10,
            section="SENIOR_SECONDARY",
        )
        self.classroom = ClassRoom.objects.create(name="SS 1A", grade_level=self.grade10)

        # Operational Subject and Topic
        self.subject = Subject.objects.create(name="Accounting", subject_code="ACC101")
        self.topic = Topic.objects.create(name="Introduction to Bookkeeping", grade_level=self.grade10, subject=self.subject)
        self.subtopic = SubTopic.objects.create(name="Ledger Accounts", topic=self.topic)

        # Official Curriculum Domain
        self.curriculum = Curriculum.objects.create(name="NERDC National Curriculum", version="2025")
        self.curriculum_subject = CurriculumSubject.objects.create(
            curriculum=self.curriculum,
            name="Accounting",
            code="ACC",
            subject=self.subject,
            grade_level=self.grade10,
        )
        self.curriculum_topic = CurriculumTopic.objects.create(
            curriculum_subject=self.curriculum_subject,
            name="Introduction to Bookkeeping",
            topic=self.topic,
            order=1,
            theme="Financial Accounting Principles",
        )
        self.curriculum_topic.subtopics.add(self.subtopic)

        self.objective = LearningObjective.objects.create(
            curriculum_topic=self.curriculum_topic,
            subtopic=self.subtopic,
            description="Understand debit and credit rules",
            order=1,
        )

        # Official Published Scheme
        self.published_scheme = PublishedScheme.objects.create(
            curriculum_subject=self.curriculum_subject,
            name="NERDC Accounting Term 1 Scheme",
            version="1.0",
        )
        self.published_entry = PublishedSchemeEntry.objects.create(
            published_scheme=self.published_scheme,
            term_number=1,
            order=1,
            week_start=1,
            week_end=2,
            entry_type=PublishedSchemeEntryType.INSTRUCTION,
            curriculum_topic=self.curriculum_topic,
            title="Introduction to Double Entry",
        )
        self.published_entry.subtopics.add(self.subtopic)
        self.published_entry.learning_objectives.add(self.objective)

        # Operational Users & Teachers
        self.admin_user = CustomUser.objects.create_user(
            email="admin@school.test",
            password=None,
            is_admin=True,
        )
        self.teacher_user = CustomUser.objects.create_user(
            email="john@school.test",
            password=None,
            is_teacher=True,
        )
        self.teacher = Teacher.objects.create(user=self.teacher_user)

    def test_operational_subject_deletion_preserves_curriculum_domain_and_names(self):
        """
        Deleting an operational Subject must:
        - Cascade-delete operational Topics.
        - Set CurriculumSubject.subject to NULL (preserving canonical name and code).
        - Set CurriculumTopic.topic to NULL (preserving canonical name).
        - Set SubTopic.topic to NULL.
        - Preserve Curriculum, CurriculumSubject, CurriculumTopic, SubTopic, LearningObjective, PublishedScheme, PublishedSchemeEntry.
        """
        subject_id = self.subject.id
        topic_id = self.topic.id

        # Delete the operational Subject
        self.subject.delete()

        # Operational Subject & Topic are deleted
        assert not Subject.objects.filter(id=subject_id).exists()
        assert not Topic.objects.filter(id=topic_id).exists()

        # Curriculum records survive intact
        self.curriculum.refresh_from_db()
        assert self.curriculum.name == "NERDC National Curriculum"

        self.curriculum_subject.refresh_from_db()
        assert self.curriculum_subject.subject is None
        assert self.curriculum_subject.name == "Accounting"
        assert self.curriculum_subject.code == "ACC"
        assert str(self.curriculum_subject) == "NERDC National Curriculum (2025) - Accounting - SS 1"

        self.curriculum_topic.refresh_from_db()
        assert self.curriculum_topic.topic is None
        assert self.curriculum_topic.name == "Introduction to Bookkeeping"
        assert self.curriculum_topic.theme == "Financial Accounting Principles"
        assert self.curriculum_topic.subtopics.filter(id=self.subtopic.id).exists()

        self.subtopic.refresh_from_db()
        assert self.subtopic.topic is None
        assert self.subtopic.name == "Ledger Accounts"

        self.objective.refresh_from_db()
        assert self.objective.curriculum_topic == self.curriculum_topic
        assert self.objective.subtopic == self.subtopic
        assert self.objective.description == "Understand debit and credit rules"

        self.published_scheme.refresh_from_db()
        assert self.published_scheme.curriculum_subject == self.curriculum_subject

        self.published_entry.refresh_from_db()
        assert self.published_entry.curriculum_topic == self.curriculum_topic
        assert self.published_entry.subtopics.filter(id=self.subtopic.id).exists()
        assert self.published_entry.learning_objectives.filter(id=self.objective.id).exists()

    def test_operational_subject_deletion_preserves_school_scheme_of_work(self):
        """
        School Scheme of Work and SchemeOfWorkItems survive operational Subject deletion.
        """
        # Adopt scheme into school SchemeOfWork
        scheme, created, skipped = PublishedSchemeAdoptionService.adopt(
            published_scheme=self.published_scheme,
            academic_year=self.year,
            term=self.term1,
            actor=self.admin_user,
        )
        assert scheme.items.count() == 1
        item = scheme.items.first()
        assert item.curriculum_topic == self.curriculum_topic

        # Delete operational Subject
        self.subject.delete()

        # Scheme of Work and Item survive intact
        scheme.refresh_from_db()
        item.refresh_from_db()
        assert scheme.curriculum_subject == self.curriculum_subject
        assert scheme.curriculum_subject.name == "Accounting"
        assert item.curriculum_topic == self.curriculum_topic
        assert item.curriculum_topic.name == "Introduction to Bookkeeping"
        assert item.subtopics.filter(id=self.subtopic.id).exists()
        assert item.learning_objectives.filter(id=self.objective.id).exists()

    def test_admin_can_adopt_unmapped_curriculum_subject(self):
        """
        Administrators can adopt a published scheme whose CurriculumSubject has NO operational Subject mapping.
        """
        self.curriculum_subject.subject = None
        self.curriculum_subject.save()

        scheme, created, skipped = PublishedSchemeAdoptionService.adopt(
            published_scheme=self.published_scheme,
            academic_year=self.year,
            term=self.term1,
            actor=self.admin_user,
        )
        assert scheme.status == SchemeOfWorkStatus.DRAFT
        assert scheme.created_by == self.admin_user
        assert scheme.responsible_teacher is None

    def test_teacher_cannot_adopt_unmapped_curriculum_subject(self):
        """
        Non-admin teachers cannot adopt an unmapped CurriculumSubject (requires subject mapping + teaching allocation).
        """
        self.curriculum_subject.subject = None
        self.curriculum_subject.save()

        with self.assertRaises(PermissionDenied):
            PublishedSchemeAdoptionService.adopt(
                published_scheme=self.published_scheme,
                academic_year=self.year,
                term=self.term1,
                actor=self.teacher_user,
            )

    def test_teacher_can_adopt_mapped_curriculum_subject_with_matching_allocation(self):
        """
        Teachers with matching AllocatedSubject can adopt a mapped CurriculumSubject.
        """
        AllocatedSubject.objects.create(
            teacher_name=self.teacher,
            subject=self.subject,
            class_room=self.classroom,
            academic_year=self.year,
            term=self.term1,
            weekly_periods=4,
        )

        scheme, created, skipped = PublishedSchemeAdoptionService.adopt(
            published_scheme=self.published_scheme,
            academic_year=self.year,
            term=self.term1,
            actor=self.teacher_user,
        )
        assert scheme.status == SchemeOfWorkStatus.DRAFT
        assert scheme.created_by == self.teacher_user
        assert scheme.responsible_teacher == self.teacher

    def test_v2_import_creates_canonical_content_without_operational_mappings(self):
        payload = {
            "schema_version": "2.0",
            "curriculum": {"name": self.curriculum.name, "version": self.curriculum.version},
            "source": {"title": "Unmapped canonical source"},
            "grades": [{
                "grade": self.grade10.system_code,
                "subjects": [{
                    "subject": "Robotics and Automation",
                    "topics": [{
                        "name": "Autonomous Systems",
                        "topic_key": "autonomous-systems",
                        "order": 1,
                        "theme": "Control",
                        "content_summary": "",
                        "subtopics": [{"name": "Feedback loops", "order": 1}],
                        "learning_objectives": [],
                        "guidance": None,
                    }],
                    "published_schemes": [],
                    "resources": [],
                }],
            }],
        }

        CurriculumImportService.import_content(data=payload, curriculum=self.curriculum)

        canonical_subject = CurriculumSubject.objects.get(
            curriculum=self.curriculum,
            grade_level=self.grade10,
            name="Robotics and Automation",
        )
        assert canonical_subject.subject is None
        canonical_topic = canonical_subject.curriculum_topics.get(name="Autonomous Systems")
        assert canonical_topic.topic is None
        canonical_subtopic = canonical_topic.subtopics.get(name="Feedback loops")
        assert canonical_subtopic.topic is None

    def test_shared_operational_topic_does_not_force_single_curriculum_owner(self):
        alternate_subject = CurriculumSubject.objects.create(
            curriculum=self.curriculum,
            name="Applied Accounting",
            code="AACC",
            subject=self.subject,
            grade_level=self.grade10,
        )
        alternate_topic = CurriculumTopic.objects.create(
            curriculum_subject=alternate_subject,
            name="Applied Bookkeeping",
            topic=self.topic,
            order=1,
        )
        alternate_topic.subtopics.add(self.subtopic)

        assert self.curriculum_topic.subtopics.filter(pk=self.subtopic.pk).exists()
        assert alternate_topic.subtopics.filter(pk=self.subtopic.pk).exists()

    def test_lesson_plan_allocation_protects_operational_subject_deletion(self):
        """
        A LessonPlan has an operational dependency on AllocatedSubject (classroom timetable delivery).
        Deleting an operational Subject that has active LessonPlans is legitimately protected by LessonPlan.allocation.
        """
        allocation = AllocatedSubject.objects.create(
            teacher_name=self.teacher,
            subject=self.subject,
            class_room=self.classroom,
            academic_year=self.year,
            term=self.term1,
            weekly_periods=4,
        )
        scheme, created, skipped = PublishedSchemeAdoptionService.adopt(
            published_scheme=self.published_scheme,
            academic_year=self.year,
            term=self.term1,
            actor=self.admin_user,
        )
        item = scheme.items.first()

        LessonPlan.objects.create(
            scheme_item=item,
            allocation=allocation,
            lesson_date="2025-09-10",
            duration_minutes=45,
            title="First Accounting Lesson",
        )

        # Attempting to delete the operational Subject should raise ProtectedError on LessonPlan.allocation
        with self.assertRaises(ProtectedError):
            self.subject.delete()
