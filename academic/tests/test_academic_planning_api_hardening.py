from django.urls import reverse
from rest_framework.test import APIClient

from administration.models import AcademicYear, Term
from academic.models import (
    AllocatedSubject, ClassRoom, Curriculum, CurriculumSubject, CurriculumTopic,
    GradeLevel, LearningObjective, LessonPlan, LessonPlanMaterial, LessonPlanStatus, SchemeOfWork,
    PublishedScheme, PublishedSchemeEntry, SchemeOfWorkItem, SchemeOfWorkStatus,
    CurriculumResource, Subject, SubTopic, Teacher, Topic,
)
from school.testcases import TenantTestCase
from tenants.models import TenantStatus
from users.models import CustomUser


class AcademicPlanningApiHardeningTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.name = "Planning API School"
        tenant.status = TenantStatus.ACTIVE

    @classmethod
    def setup_domain(cls, domain):
        domain.is_primary = True
        return domain

    def setUp(self):
        self.admin_user = CustomUser.objects.create_user(
            email="admin@planning.test", password="x", is_admin=True
        )
        self.owner_user = CustomUser.objects.create_user(
            email="owner@planning.test", password="x", is_teacher=True
        )
        self.other_user = CustomUser.objects.create_user(
            email="other@planning.test", password="x", is_teacher=True
        )
        self.ordinary_user = CustomUser.objects.create_user(
            email="ordinary@planning.test", password="x"
        )
        self.owner = Teacher.objects.create(user=self.owner_user)
        self.other = Teacher.objects.create(user=self.other_user)
        self.grade = GradeLevel.objects.create(
            system_code="JSS_1", default_name="JSS 1", section="JSS", sequence_order=10
        )
        self.classroom = ClassRoom.objects.create(name="A", grade_level=self.grade)
        self.year = AcademicYear.objects.create(
            name="2025/2026", start_date="2025-09-01", end_date="2026-07-31", active_year=True
        )
        self.term = Term.objects.create(
            name="First Term", academic_year=self.year,
            start_date="2025-09-01", end_date="2025-12-15"
        )
        self.subject = Subject.objects.create(name="Mathematics", subject_code="MATH")
        self.curriculum = Curriculum.objects.create(name="Standard")
        self.curriculum_subject = CurriculumSubject.objects.create(
            curriculum=self.curriculum, subject=self.subject, grade_level=self.grade
        )
        self.topic = Topic.objects.create(
            name="Algebra", subject=self.subject, grade_level=self.grade
        )
        self.curriculum_topic = CurriculumTopic.objects.create(
            curriculum_subject=self.curriculum_subject, topic=self.topic
        )
        self.subtopic = SubTopic.objects.create(name="Expressions", topic=self.topic)
        self.objective = LearningObjective.objects.create(
            curriculum_topic=self.curriculum_topic, subtopic=self.subtopic,
            description="Simplify expressions"
        )
        self.scheme = SchemeOfWork.objects.create(
            academic_year=self.year, term=self.term,
            curriculum_subject=self.curriculum_subject,
            responsible_teacher=self.owner, created_by=self.owner_user,
        )
        self.item = SchemeOfWorkItem.objects.create(
            scheme=self.scheme, week_start=1, curriculum_topic=self.curriculum_topic
        )
        self.item.subtopics.add(self.subtopic)
        self.item.learning_objectives.add(self.objective)
        self.allocation = AllocatedSubject.objects.create(
            teacher_name=self.owner, subject=self.subject, class_room=self.classroom,
            academic_year=self.year, term=self.term, weekly_periods=2
        )
        self.plan = LessonPlan.objects.create(
            scheme_item=self.item, allocation=self.allocation,
            lesson_date="2025-10-01", title="Expressions"
        )
        self.plan.subtopics.add(self.subtopic)
        self.plan.learning_objectives.add(self.objective)

        self.owner_client = APIClient(HTTP_HOST=self.domain.domain)
        self.owner_client.force_authenticate(self.owner_user)
        self.other_client = APIClient(HTTP_HOST=self.domain.domain)
        self.other_client.force_authenticate(self.other_user)
        self.admin_client = APIClient(HTTP_HOST=self.domain.domain)
        self.admin_client.force_authenticate(self.admin_user)
        self.ordinary_client = APIClient(HTTP_HOST=self.domain.domain)
        self.ordinary_client.force_authenticate(self.ordinary_user)

    def test_scheme_create_assigns_actor_and_ignores_spoofed_creator(self):
        other_subject = Subject.objects.create(name="English", subject_code="ENG")
        mapping = CurriculumSubject.objects.create(
            curriculum=self.curriculum, subject=other_subject, grade_level=self.grade
        )
        response = self.owner_client.post(reverse("scheme-of-work-list"), {
            "academic_year": self.year.id, "term": self.term.id,
            "curriculum_subject": mapping.id, "created_by": self.other.id,
            "teacher": self.other.id,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["created_by"], self.owner_user.id)
        self.assertEqual(response.data["responsible_teacher"], self.owner.id)

    def test_admin_without_teacher_can_create_and_manage_scheme_with_correct_audit_actor(self):
        other_subject = Subject.objects.create(name="Civic Education", subject_code="CIV")
        mapping = CurriculumSubject.objects.create(
            curriculum=self.curriculum, subject=other_subject, grade_level=self.grade
        )
        created = self.admin_client.post(reverse("scheme-of-work-list"), {
            "academic_year": self.year.id, "term": self.term.id,
            "curriculum_subject": mapping.id,
        }, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["created_by"], self.admin_user.id)
        self.assertIsNone(created.data["responsible_teacher"])
        updated = self.admin_client.patch(
            reverse("scheme-of-work-detail", args=[created.data["id"]]),
            {"is_active": False}, format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.data)

    def test_admin_without_teacher_or_allocation_can_adopt_with_correct_audit_actor(self):
        self.scheme.is_active = False
        self.scheme.save(update_fields=["is_active"])
        published, _, _ = self._published_scheme()
        payload = {"published_scheme": published.id, "academic_year": self.year.id, "term": self.term.id}
        capability = self.admin_client.get(reverse("scheme-of-work-adoption-capability"), payload)
        self.assertEqual(capability.status_code, 200, capability.data)
        self.assertTrue(capability.data["allowed"])
        response = self.admin_client.post(reverse("scheme-of-work-adopt-published"), payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        adopted = SchemeOfWork.objects.get(pk=response.data["scheme"]["id"])
        self.assertEqual(adopted.created_by, self.admin_user)
        self.assertIsNone(adopted.responsible_teacher)

    def test_admin_can_adopt_into_existing_scheme_without_teacher_profile(self):
        published, _, _ = self._published_scheme()
        payload = {"published_scheme": published.id, "academic_year": self.year.id, "term": self.term.id}
        response = self.admin_client.post(reverse("scheme-of-work-adopt-published"), payload, format="json")
        self.assertIn(response.status_code, [200, 201], response.data)
        self.scheme.refresh_from_db()
        self.assertEqual(self.scheme.responsible_teacher, self.owner)

    def test_adoption_policy_allows_allocated_teacher_and_denies_other_actors(self):
        published, _, _ = self._published_scheme()
        payload = {"published_scheme": published.id, "academic_year": self.year.id, "term": self.term.id}
        allocated = self.owner_client.get(reverse("scheme-of-work-adoption-capability"), payload)
        unallocated = self.other_client.get(reverse("scheme-of-work-adoption-capability"), payload)
        ordinary = self.ordinary_client.post(reverse("scheme-of-work-adopt-published"), payload, format="json")
        self.assertTrue(allocated.data["allowed"])
        self.assertFalse(unallocated.data["allowed"])
        self.assertEqual(ordinary.status_code, 403)

    def test_teacher_cannot_enumerate_or_mutate_another_teachers_records(self):
        schemes = self.other_client.get(reverse("scheme-of-work-list"))
        plans = self.other_client.get(reverse("lesson-plan-list"))
        self.assertEqual(schemes.data["count"], 0)
        self.assertEqual(plans.data["count"], 0)
        self.assertEqual(self.other_client.patch(
            reverse("scheme-of-work-detail", args=[self.scheme.id]), {"is_active": False}
        ).status_code, 404)
        self.assertEqual(self.other_client.delete(
            reverse("lesson-plan-detail", args=[self.plan.id])
        ).status_code, 404)

    def test_submitted_parent_and_children_are_immutable(self):
        self.scheme.status = SchemeOfWorkStatus.SUBMITTED
        self.scheme.save(update_fields=["status"])
        self.assertEqual(self.owner_client.patch(
            reverse("scheme-of-work-detail", args=[self.scheme.id]), {"is_active": False}
        ).status_code, 400)
        self.assertEqual(self.owner_client.patch(
            reverse("scheme-of-work-item-detail", args=[self.item.id]), {"notes": "changed"}
        ).status_code, 400)

    def test_submitted_plan_and_materials_are_immutable(self):
        self.plan.status = LessonPlanStatus.SUBMITTED
        self.plan.save(update_fields=["status"])
        self.assertEqual(self.owner_client.patch(
            reverse("lesson-plan-detail", args=[self.plan.id]), {"title": "changed"}
        ).status_code, 400)
        response = self.owner_client.post(reverse("lesson-plan-material-list"), {
            "lesson_plan": self.plan.id, "title": "Text", "external_url": "https://example.com/text"
        }, format="json")
        self.assertEqual(response.status_code, 400)

    def test_scheme_item_m2m_scope_validation_runs_through_api(self):
        foreign_topic = Topic.objects.create(
            name="Grammar", subject=self.subject, grade_level=self.grade
        )
        foreign_subtopic = SubTopic.objects.create(name="Nouns", topic=foreign_topic)
        response = self.owner_client.patch(
            reverse("scheme-of-work-item-detail", args=[self.item.id]),
            {"subtopics": [foreign_subtopic.id]}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_lesson_plan_m2m_scope_validation_runs_through_api(self):
        extra_objective = LearningObjective.objects.create(
            curriculum_topic=self.curriculum_topic, description="Not selected in scheme", order=2
        )
        response = self.owner_client.patch(
            reverse("lesson-plan-detail", args=[self.plan.id]),
            {"learning_objectives": [extra_objective.id]}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_teacher_cannot_mutate_official_curriculum(self):
        response = self.owner_client.patch(
            reverse("curriculum-detail", args=[self.curriculum.id]),
            {"name": "Teacher edit"}, format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_lesson_delivery_api_is_scoped_and_validates_coverage(self):
        invalid_objective = LearningObjective.objects.create(
            curriculum_topic=self.curriculum_topic, description="Unplanned", order=2
        )
        invalid = self.owner_client.post(reverse("lesson-delivery-list"), {
            "lesson_plan": self.plan.id,
            "status": "COMPLETED",
            "objectives_covered": [invalid_objective.id],
        }, format="json")
        self.assertEqual(invalid.status_code, 400, invalid.data)
        valid = self.owner_client.post(reverse("lesson-delivery-list"), {
            "lesson_plan": self.plan.id,
            "status": "COMPLETED",
            "objectives_covered": [self.objective.id],
            "subtopics_covered": [self.subtopic.id],
        }, format="json")
        self.assertEqual(valid.status_code, 201, valid.data)
        self.assertEqual(valid.data["recorded_by"], self.owner.id)
        self.assertEqual(
            self.other_client.get(reverse("lesson-delivery-list")).data["count"], 0
        )

    def _published_scheme(self):
        published = PublishedScheme.objects.create(
            curriculum_subject=self.curriculum_subject,
            name="Official Mathematics", version="2025", is_active=True,
        )
        instruction = PublishedSchemeEntry.objects.create(
            published_scheme=published, term_number=1, week_start=2, week_end=3,
            entry_type="INSTRUCTION", curriculum_topic=self.curriculum_topic,
            title="Official Expressions", content_summary="Official scope",
            teacher_activities="Demonstrate", pupil_activities="Practise",
            learning_resources="Textbook", order=1,
        )
        instruction.subtopics.add(self.subtopic)
        instruction.learning_objectives.add(self.objective)
        break_entry = PublishedSchemeEntry.objects.create(
            published_scheme=published, term_number=1, week_start=4,
            entry_type="BREAK", title="Midterm Break", order=2,
        )
        return published, instruction, break_entry

    def test_adoption_copies_ranges_topicless_rows_and_provenance(self):
        published, instruction, break_entry = self._published_scheme()
        response = self.owner_client.post(
            reverse("scheme-of-work-adopt-published"),
            {"published_scheme": published.id, "academic_year": self.year.id, "term": self.term.id},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["created_items"], 2)
        adopted = SchemeOfWorkItem.objects.get(published_scheme_entry=instruction)
        self.assertEqual((adopted.week_start, adopted.week_end), (2, 3))
        self.assertEqual(adopted.learner_activities, "Practise")
        self.assertEqual(list(adopted.subtopics.all()), [self.subtopic])
        operational_break = SchemeOfWorkItem.objects.get(published_scheme_entry=break_entry)
        self.assertIsNone(operational_break.curriculum_topic)
        self.assertEqual(operational_break.entry_type, "BREAK")

    def test_repeated_adoption_is_idempotent_and_does_not_overwrite_edits(self):
        published, instruction, _ = self._published_scheme()
        payload = {"published_scheme": published.id, "academic_year": self.year.id, "term": self.term.id}
        first = self.owner_client.post(reverse("scheme-of-work-adopt-published"), payload, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        item = SchemeOfWorkItem.objects.get(published_scheme_entry=instruction)
        item.title = "School-adapted title"
        item.save(update_fields=["title"])
        second = self.owner_client.post(reverse("scheme-of-work-adopt-published"), payload, format="json")
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(second.data["created_items"], 0)
        self.assertEqual(second.data["skipped_items"], 2)
        item.refresh_from_db()
        self.assertEqual(item.title, "School-adapted title")

    def test_scheme_workspace_contract_exposes_source_lineage_and_backend_capabilities(self):
        published, instruction, _ = self._published_scheme()
        response = self.owner_client.post(
            reverse("scheme-of-work-adopt-published"),
            {"published_scheme": published.id, "academic_year": self.year.id, "term": self.term.id},
            format="json",
        )
        self.assertIn(response.status_code, {200, 201}, response.data)
        detail = self.owner_client.get(reverse("scheme-of-work-detail", args=[self.scheme.id]))
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertEqual(detail.data["curriculum_name"], "Standard")
        self.assertEqual(detail.data["grade_level_name"], "JSS 1")
        self.assertEqual(detail.data["published_sources"], [
            {"id": published.id, "name": "Official Mathematics", "version": "2025"}
        ])
        adopted = next(item for item in detail.data["items"] if item["published_scheme_entry"] == instruction.id)
        self.assertEqual(adopted["official_source"]["title"], "Official Expressions")
        self.assertEqual(adopted["official_source"]["week_end"], 3)
        self.assertTrue(detail.data["permissions"]["can_edit"])
        self.assertTrue(detail.data["permissions"]["can_submit"])

    def test_operational_entries_support_same_week_ranges_unscheduled_and_topicless_rows(self):
        base = {
            "scheme": self.scheme.id, "subtopics": [], "learning_objectives": [],
            "notes": "", "content_summary": "", "teacher_activities": "",
            "learner_activities": "", "learning_resources": "",
        }
        same_week = self.owner_client.post(reverse("scheme-of-work-item-list"), {
            **base, "entry_type": "ASSESSMENT", "week_start": 2, "week_end": 2,
            "curriculum_topic": None, "title": "Quiz", "order": 2,
        }, format="json")
        ranged = self.owner_client.post(reverse("scheme-of-work-item-list"), {
            **base, "entry_type": "BREAK", "week_start": 2, "week_end": 3,
            "curriculum_topic": None, "title": "Break", "order": 3,
        }, format="json")
        unscheduled = self.owner_client.post(reverse("scheme-of-work-item-list"), {
            **base, "entry_type": "PREPARATION", "week_start": None, "week_end": None,
            "curriculum_topic": None, "title": "Preparation", "order": 4,
        }, format="json")
        self.assertEqual(same_week.status_code, 201, same_week.data)
        self.assertEqual(ranged.status_code, 201, ranged.data)
        self.assertEqual(unscheduled.status_code, 201, unscheduled.data)
        listed = self.owner_client.get(reverse("scheme-of-work-item-list"), {"scheme": self.scheme.id})
        self.assertEqual([item["order"] for item in listed.data["results"]], [1, 2, 3, 4])
        self.assertIsNone(unscheduled.data["curriculum_topic"])

    def test_create_lesson_plan_from_scheme_item_inherits_editable_defaults(self):
        self.item.title = "School Expressions"
        self.item.content_summary = "Simplify like terms"
        self.item.teacher_activities = "Model examples"
        self.item.learner_activities = "Solve in pairs"
        self.item.learning_resources = "Algebra tiles"
        self.item.save()
        response = self.owner_client.post(reverse("lesson-plan-create-from-scheme-item"), {
            "scheme_item": self.item.id, "allocation": self.allocation.id,
            "lesson_date": "2025-10-08", "duration_minutes": 45,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        plan = LessonPlan.objects.get(pk=response.data["id"])
        self.assertEqual(plan.title, "School Expressions")
        self.assertEqual(plan.lesson_content, "Simplify like terms")
        self.assertEqual(plan.teacher_activities, "Model examples")
        self.assertEqual(plan.learner_activities, "Solve in pairs")
        self.assertEqual(plan.teaching_materials, "Algebra tiles")
        self.assertEqual(list(plan.subtopics.all()), [self.subtopic])
        self.assertEqual(list(plan.learning_objectives.all()), [self.objective])
        edited = self.owner_client.patch(reverse("lesson-plan-detail", args=[plan.id]), {
            "lesson_content": "Teacher-adapted content",
            "teacher_activities": "Teacher-adapted activity",
        }, format="json")
        self.assertEqual(edited.status_code, 200, edited.data)
        self.item.refresh_from_db()
        self.assertEqual(self.item.content_summary, "Simplify like terms")
        self.assertEqual(self.item.teacher_activities, "Model examples")

    def test_lesson_plan_entry_type_rules_and_multiple_plans_are_explicit(self):
        second = self.owner_client.post(reverse("lesson-plan-create-from-scheme-item"), {
            "scheme_item": self.item.id, "allocation": self.allocation.id,
            "lesson_date": "2025-10-09",
        }, format="json")
        third = self.owner_client.post(reverse("lesson-plan-create-from-scheme-item"), {
            "scheme_item": self.item.id, "allocation": self.allocation.id,
            "lesson_date": "2025-10-10",
        }, format="json")
        self.assertEqual(second.status_code, 201, second.data)
        self.assertEqual(third.status_code, 201, third.data)
        break_item = SchemeOfWorkItem.objects.create(
            scheme=self.scheme, entry_type="BREAK", week_start=2,
            title="Midterm break", order=2,
        )
        prohibited = self.owner_client.post(reverse("lesson-plan-create-from-scheme-item"), {
            "scheme_item": break_item.id, "allocation": self.allocation.id,
            "lesson_date": "2025-10-11",
        }, format="json")
        self.assertEqual(prohibited.status_code, 400, prohibited.data)
        item_detail = self.owner_client.get(reverse("scheme-of-work-item-detail", args=[self.item.id]))
        self.assertTrue(item_detail.data["lesson_planning"]["multiple_plans_permitted"])
        self.assertEqual(item_detail.data["lesson_planning"]["lesson_plan_count"], 3)

    def test_curriculum_resource_suggestions_and_material_conversion(self):
        subject_resource = CurriculumResource.objects.create(
            curriculum_subject=self.curriculum_subject, resource_type="REFERENCE",
            title="Online algebra guide", content="Official reference",
            metadata={"url": "https://example.com/algebra"}, order=1,
        )
        text_resource = CurriculumResource.objects.create(
            curriculum_subject=self.curriculum_subject, curriculum_topic=self.curriculum_topic,
            resource_type="INSTRUCTIONAL_NOTE", title="Teacher note", content="Text only", order=2,
        )
        plan = self.plan
        suggestions = self.owner_client.get(
            reverse("lesson-plan-curriculum-resources", args=[plan.id])
        )
        self.assertEqual(suggestions.status_code, 200, suggestions.data)
        self.assertEqual({item["id"] for item in suggestions.data}, {subject_resource.id, text_resource.id})
        added = self.owner_client.post(
            reverse("lesson-plan-add-curriculum-resource", args=[plan.id]),
            {"curriculum_resource": subject_resource.id}, format="json",
        )
        self.assertEqual(added.status_code, 201, added.data)
        material = LessonPlanMaterial.objects.get(pk=added.data["id"])
        self.assertEqual(material.external_url, "https://example.com/algebra")
        self.assertEqual(material.title, subject_resource.title)
        self.assertTrue(CurriculumResource.objects.filter(pk=subject_resource.id).exists())
        unsupported = self.owner_client.post(
            reverse("lesson-plan-add-curriculum-resource", args=[plan.id]),
            {"curriculum_resource": text_resource.id}, format="json",
        )
        self.assertEqual(unsupported.status_code, 400, unsupported.data)

    def test_curriculum_resource_material_respects_plan_lifecycle_and_ownership(self):
        resource = CurriculumResource.objects.create(
            curriculum_subject=self.curriculum_subject, title="Guide",
            metadata={"external_url": "https://example.com/guide"},
        )
        self.plan.status = LessonPlanStatus.SUBMITTED
        self.plan.save(update_fields=["status"])
        locked = self.owner_client.post(
            reverse("lesson-plan-add-curriculum-resource", args=[self.plan.id]),
            {"curriculum_resource": resource.id}, format="json",
        )
        self.assertEqual(locked.status_code, 400, locked.data)
        hidden = self.other_client.get(
            reverse("lesson-plan-curriculum-resources", args=[self.plan.id])
        )
        self.assertEqual(hidden.status_code, 404)

    def test_adoption_requires_matching_teacher_allocation(self):
        published, _, _ = self._published_scheme()
        response = self.other_client.post(
            reverse("scheme-of-work-adopt-published"),
            {"published_scheme": published.id, "academic_year": self.year.id, "term": self.term.id},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_invalid_published_term_rolls_back_without_partial_items(self):
        published = PublishedScheme.objects.create(
            curriculum_subject=self.curriculum_subject,
            name="Invalid Official Scheme", version="2025", is_active=True,
        )
        PublishedSchemeEntry.objects.create(
            published_scheme=published, term_number=1, week_start=2,
            entry_type="BREAK", title="Valid first row", order=1,
        )
        PublishedSchemeEntry.objects.create(
            published_scheme=published, term_number=1, week_start=3,
            entry_type="INSTRUCTION", curriculum_topic=None,
            title="Invalid second row", order=2,
        )
        before = self.scheme.items.count()
        response = self.owner_client.post(
            reverse("scheme-of-work-adopt-published"),
            {"published_scheme": published.id, "academic_year": self.year.id, "term": self.term.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.scheme.items.count(), before)
