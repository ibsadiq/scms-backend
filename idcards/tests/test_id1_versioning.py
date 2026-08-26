import copy
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from rest_framework.test import APIRequestFactory, force_authenticate
from django_tenants.utils import get_public_schema_name, schema_context

from academic.models import Student
from idcards.models import HolderType, IDCardTemplateVersion
from idcards.services import CardService, IDCardTemplateLifecycleService, LayoutService, LayoutValidator
from idcards.views import IDCardTemplateVersionViewSet
from school.testcases import TenantTestCase, TenantTransactionTestCase
from tenants.models import Client, TenantStatus


User = get_user_model()


def v1(field="student.full_name"):
    return {
        "schema_version": 1,
        "elements": [{
            "id": "name", "type": "dynamic_text", "field": field,
            "x": 10, "y": 10, "width": 40, "height": 10,
        }],
    }


def v2(field="student.full_name", width="85.60", height="53.98", orientation="LANDSCAPE"):
    layout = LayoutService.empty_v2(width, height, orientation)
    layout["elements"] = [{
        "id": "name", "type": "dynamic_text", "x": 500, "y": 500,
        "width": 4000, "height": 700, "rotation": 0, "z_index": 0,
        "visible": True, "locked": False,
        "binding": {"field": field, "required": True, "hide_when_empty": False},
        "style": {}, "constraints": {},
    }]
    return layout


class ID1TemplateVersioningTests(TenantTestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="id1-admin@example.com", password="test", is_admin=True, is_staff=True,
        )
        self.teacher = User.objects.create_user(
            email="id1-teacher@example.com", password="test", is_teacher=True,
        )
        self.factory = APIRequestFactory()
        self.student = Student.objects.create(
            first_name="Amina", last_name="Bello", parent_contact="08020000011",
            admission_number="ID1-001",
        )

    def create_template(self, **overrides):
        values = {
            "name": "Student ID", "holder_type": HolderType.STUDENT,
            "actor": self.admin, "front_layout": v1(),
            "back_layout": {"schema_version": 1, "elements": []},
        }
        values.update(overrides)
        return IDCardTemplateLifecycleService.create_template(**values)

    def test_create_template_creates_draft_version_one(self):
        template = self.create_template()
        self.assertFalse(template.is_active)
        self.assertEqual(template.current_draft_version.version_number, 1)
        self.assertEqual(template.current_draft_version.status, IDCardTemplateVersion.Status.DRAFT)
        self.assertIsNone(template.current_published_version)

    def test_invalid_holder_type_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.create_template(name="Invalid", holder_type="PARENT")

    def test_version_numbers_increase_and_only_one_draft_exists(self):
        template = self.create_template()
        first = IDCardTemplateLifecycleService.publish(template.current_draft_version, actor=self.admin)
        draft = IDCardTemplateLifecycleService.create_draft(template, actor=self.admin)
        self.assertEqual(draft.version_number, 2)
        self.assertEqual(draft.created_from_version, first)
        self.assertEqual(IDCardTemplateLifecycleService.create_draft(template, actor=self.admin), draft)
        with self.assertRaises(IntegrityError), transaction.atomic():
            IDCardTemplateVersion.objects.create(
                template=template, version_number=3, status=IDCardTemplateVersion.Status.DRAFT,
            )

    def test_publish_is_immutable_and_editing_creates_a_draft(self):
        template = self.create_template()
        published = IDCardTemplateLifecycleService.publish(template.current_draft_version, actor=self.admin)
        published.front_layout = {"schema_version": 1, "elements": []}
        with self.assertRaises(ValidationError):
            published.save()
        draft = IDCardTemplateLifecycleService.create_draft(template, actor=self.admin)
        changed = copy.deepcopy(draft.front_layout)
        changed["elements"][0]["x"] = 12
        IDCardTemplateLifecycleService.update_draft(draft, front_layout=changed)
        published.refresh_from_db()
        self.assertEqual(published.front_layout["elements"][0]["x"], 10)

    def test_archived_versions_remain_readable(self):
        template = self.create_template()
        first = IDCardTemplateLifecycleService.publish(template.current_draft_version, actor=self.admin)
        second = IDCardTemplateLifecycleService.create_draft(template, actor=self.admin)
        IDCardTemplateLifecycleService.publish(second, actor=self.admin)
        first.refresh_from_db()
        self.assertEqual(first.status, IDCardTemplateVersion.Status.ARCHIVED)
        self.assertEqual(first.front_layout, v1())

    def test_v1_is_read_without_conversion(self):
        layout = v1()
        original = copy.deepcopy(layout)
        self.assertIs(LayoutService.read(layout, HolderType.STUDENT), layout)
        self.assertEqual(layout, original)

    def test_v2_dimensions_follow_physical_orientation(self):
        self.assertEqual(LayoutValidator.canvas_dimensions("85.60", "53.98", "LANDSCAPE"), (10000, 6306))
        self.assertEqual(LayoutValidator.canvas_dimensions("53.98", "85.60", "PORTRAIT"), (6306, 10000))
        LayoutValidator.validate(
            v2(), HolderType.STUDENT, width_mm="85.60", height_mm="53.98", orientation="LANDSCAPE",
        )

    def test_v2_rejects_malformed_bounds_ids_z_order_and_cross_holder_binding(self):
        cases = []
        outside = v2(); outside["elements"][0]["x"] = 9000; cases.append(outside)
        duplicate = v2(); duplicate["elements"].append(copy.deepcopy(duplicate["elements"][0])); cases.append(duplicate)
        z_duplicate = v2(); second = copy.deepcopy(z_duplicate["elements"][0]); second["id"] = "other"; z_duplicate["elements"].append(second); cases.append(z_duplicate)
        cases.append(v2("staff.full_name"))
        for layout in cases:
            with self.subTest(layout=layout), self.assertRaises(ValidationError):
                LayoutValidator.validate(
                    layout, HolderType.STUDENT, width_mm="85.60", height_mm="53.98", orientation="LANDSCAPE",
                )

    def test_issue_and_replacement_retain_exact_version(self):
        template = self.create_template()
        first = IDCardTemplateLifecycleService.publish(template.current_draft_version, actor=self.admin)
        card = CardService.issue_student_card(student=self.student, template=template, issued_by=self.admin)
        second = IDCardTemplateLifecycleService.create_draft(template, actor=self.admin)
        IDCardTemplateLifecycleService.publish(second, actor=self.admin)
        replacement = CardService.replace_card(card, actor=self.admin, reason="Damaged")
        card.refresh_from_db()
        self.assertEqual(card.template_version_id, first.pk)
        self.assertEqual(replacement.template_version_id, first.pk)
        self.assertNotEqual(replacement.template_version_id, template.current_published_version_id)

    def test_archive_preserves_versions_and_blocks_new_edits(self):
        template = self.create_template()
        version = template.current_draft_version
        IDCardTemplateLifecycleService.archive(template)
        version.refresh_from_db()
        self.assertEqual(version.status, IDCardTemplateVersion.Status.ARCHIVED)
        self.assertTrue(version.template.versions.filter(pk=version.pk).exists())
        with self.assertRaises(ValidationError):
            IDCardTemplateLifecycleService.create_draft(template, actor=self.admin)

    def test_version_api_allows_admin_and_denies_unauthorized_roles(self):
        template = self.create_template()
        version = template.current_draft_version
        view = IDCardTemplateVersionViewSet.as_view({"post": "publish"})
        anonymous = view(self.factory.post("/publish/", {}, format="json"), pk=version.pk)
        self.assertEqual(anonymous.status_code, 401)
        teacher_request = self.factory.post("/publish/", {}, format="json")
        force_authenticate(teacher_request, user=self.teacher)
        self.assertEqual(view(teacher_request, pk=version.pk).status_code, 403)
        admin_request = self.factory.post("/publish/", {}, format="json")
        force_authenticate(admin_request, user=self.admin)
        response = view(admin_request, pk=version.pk)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], IDCardTemplateVersion.Status.PUBLISHED)

    def test_version_api_refuses_patch_to_published_layout(self):
        template = self.create_template()
        version = IDCardTemplateLifecycleService.publish(template.current_draft_version, actor=self.admin)
        request = self.factory.patch(
            "/version/", {"front_layout": {"schema_version": 1, "elements": []}}, format="json",
        )
        force_authenticate(request, user=self.admin)
        response = IDCardTemplateVersionViewSet.as_view({"patch": "partial_update"})(request, pk=version.pk)
        self.assertEqual(response.status_code, 400)
        version.refresh_from_db()
        self.assertEqual(version.front_layout, v1())


class ID1TemplateTenantIsolationTests(TenantTransactionTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = "ID1 Tenant A"
        tenant.status = TenantStatus.ACTIVE

    def setUp(self):
        with schema_context(self.tenant.schema_name):
            self.admin_a = User.objects.create_user(
                email="id1-tenant-a@example.com", password="test", is_admin=True, is_staff=True,
            )
            template = IDCardTemplateLifecycleService.create_template(
                name="Tenant A Template", holder_type=HolderType.STUDENT, actor=self.admin_a,
                front_layout=v1(), back_layout={"schema_version": 1, "elements": []},
            )
            self.version_id = template.current_draft_version_id

        suffix = uuid.uuid4().hex[:10]
        with schema_context(get_public_schema_name()):
            self.tenant_b = Client(
                schema_name=f"test_id1_b_{suffix}", name="ID1 Tenant B", status=TenantStatus.ACTIVE,
            )
            self.tenant_b.auto_create_schema = True
            self.tenant_b.save(verbosity=0)
        with schema_context(self.tenant_b.schema_name):
            self.admin_b = User.objects.create_user(
                email=f"id1-tenant-b-{suffix}@example.com", password="test", is_admin=True, is_staff=True,
            )

    def tearDown(self):
        with schema_context(get_public_schema_name()):
            self.tenant_b.delete(force_drop=True)

    def test_cross_tenant_template_version_id_does_not_resolve(self):
        with schema_context(self.tenant_b.schema_name):
            request = APIRequestFactory().get(f"/api/idcards/template-versions/{self.version_id}/")
            force_authenticate(request, user=self.admin_b)
            response = IDCardTemplateVersionViewSet.as_view({"get": "retrieve"})(
                request, pk=self.version_id,
            )
            self.assertEqual(response.status_code, 404)


class ID1TemplateMigrationTests(TenantTransactionTestCase):
    def tearDown(self):
        try:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
        finally:
            super().tearDown()

    def test_legacy_templates_and_cards_are_backfilled_without_layout_conversion(self):
        old_target = [("idcards", "0003_active_card_replacement")]
        new_target = [("idcards", "0004_template_versioning_foundation")]
        executor = MigrationExecutor(connection)
        executor.migrate(old_target)
        old_apps = executor.loader.project_state(old_target).apps
        Template = old_apps.get_model("idcards", "IDCardTemplate")
        Card = old_apps.get_model("idcards", "IDCard")
        original_front = v1()
        original_back = {"schema_version": 1, "elements": []}
        active = Template.objects.create(
            name="Legacy Active", holder_type="STUDENT", is_active=True,
            front_layout=copy.deepcopy(original_front), back_layout=copy.deepcopy(original_back),
        )
        inactive = Template.objects.create(
            name="Legacy Inactive", holder_type="STUDENT", is_active=False,
            front_layout=copy.deepcopy(original_front), back_layout=copy.deepcopy(original_back),
        )
        with connection.cursor() as cursor:
            cursor.execute(
                'INSERT INTO "academic_student" (student_id, first_name, last_name, parent_contact, admission_number, is_active, can_login) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id',
                ["STU-LEGACY001", "Legacy", "Holder", "08000000000", "LEGACY-ID1", True, False],
            )
            student_id = cursor.fetchone()[0]
        card = Card.objects.create(student_id=student_id, template=active, card_number="IDC-LEGACY-1")

        executor = MigrationExecutor(connection)
        executor.migrate(new_target)
        new_apps = executor.loader.project_state(new_target).apps
        Template = new_apps.get_model("idcards", "IDCardTemplate")
        Version = new_apps.get_model("idcards", "IDCardTemplateVersion")
        Card = new_apps.get_model("idcards", "IDCard")
        active = Template.objects.get(pk=active.pk)
        inactive = Template.objects.get(pk=inactive.pk)
        active_version = Version.objects.get(template_id=active.pk, version_number=1)
        inactive_version = Version.objects.get(template_id=inactive.pk, version_number=1)
        migrated_card = Card.objects.get(pk=card.pk)

        self.assertEqual(active_version.status, "PUBLISHED")
        self.assertEqual(active.current_published_version_id, active_version.pk)
        self.assertFalse(active.is_archived)
        self.assertEqual(inactive_version.status, "ARCHIVED")
        self.assertTrue(inactive.is_archived)
        self.assertIsNone(inactive.current_published_version_id)
        self.assertEqual(active_version.front_layout, original_front)
        self.assertEqual(active_version.back_layout, original_back)
        self.assertEqual(migrated_card.template_version_id, active_version.pk)
