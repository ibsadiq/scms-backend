from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from school.testcases import TenantTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from academic.models import Staff, Student
from idcards.models import HolderType, IDCard, IDCardTemplate, RFIDCredential
from idcards.services import BrandingResolver, CardService, DynamicFieldRegistry, RFIDCredentialService
from idcards.views import IDCardTemplateViewSet, IDCardViewSet, template_fields


User = get_user_model()


def layout(field=None, element_type="text"):
    element = {"id": "element-1", "type": element_type, "x": 1, "y": 2, "width": 30, "height": 8}
    if field:
        element["field"] = field
    return {"schema_version": 1, "elements": [element]}


class IDCardFoundationTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.name = "SSync Academy"
        tenant.motto = "Learn and lead"
        tenant.address = "1 School Road"
        tenant.contact_phone = "08000000000"
        tenant.contact_email = "hello@ssync.test"
        return super().setup_tenant(tenant)

    def setUp(self):
        self.admin = User.objects.create_user(email="cards-admin@example.com", password="test", is_admin=True, is_staff=True)
        self.teacher = User.objects.create_user(email="cards-teacher@example.com", password="test", is_teacher=True)
        staff_user = User.objects.create_user(
            email="staff-card@example.com", password="test", first_name="Grace", last_name="Okafor"
        )
        self.student = Student.objects.create(
            first_name="amina", last_name="bello", parent_contact="08020000011", admission_number="ADM-CARD-1"
        )
        self.staff = Staff.objects.create(user=staff_user, designation="Bursar", role=Staff.Role.ACCOUNTANT)
        self.student_template = IDCardTemplate.objects.create(
            name="Student Standard", holder_type=HolderType.STUDENT,
            front_layout=layout("student.full_name", "dynamic_text"), back_layout=layout("card.card_number", "barcode"),
        )
        self.staff_template = IDCardTemplate.objects.create(
            name="Staff Standard", holder_type=HolderType.STAFF,
            front_layout=layout("staff.full_name", "dynamic_text"), back_layout=layout("card.verification_token", "qr"),
        )
        self.factory = APIRequestFactory()

    def test_creates_student_and_staff_templates_with_cr80_mm_defaults(self):
        self.student_template.full_clean()
        self.staff_template.full_clean()
        self.assertEqual(str(self.student_template.width_mm), "85.60")
        self.assertEqual(str(self.student_template.height_mm), "53.98")

    def test_layout_validation_rejects_structure_types_ids_and_dimensions(self):
        invalid_layouts = [
            [], {"schema_version": 2, "elements": []},
            {"schema_version": 1, "elements": [{"id": "x", "type": "script", "x": 0, "y": 0, "width": 1, "height": 1}]},
            {"schema_version": 1, "elements": [layout()["elements"][0], layout()["elements"][0]]},
            {"schema_version": 1, "elements": [{"id": "x", "type": "text", "x": -1, "y": 0, "width": 1, "height": 1}]},
        ]
        for value in invalid_layouts:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                IDCardTemplate(name="Bad", holder_type=HolderType.STUDENT, front_layout=value).full_clean()

    def test_unknown_and_cross_holder_fields_are_rejected(self):
        for holder_type, key in [
            (HolderType.STUDENT, "student.password"),
            (HolderType.STUDENT, "staff.full_name"),
            (HolderType.STAFF, "student.full_name"),
        ]:
            with self.subTest(holder_type=holder_type, key=key), self.assertRaises(ValidationError):
                IDCardTemplate(
                    name=f"Bad {key}", holder_type=holder_type,
                    front_layout=layout(key, "dynamic_text"), back_layout={"schema_version": 1, "elements": []},
                ).full_clean()

    def test_issue_student_and_staff_cards_with_readable_unique_numbers(self):
        student_card = CardService.issue_student_card(student=self.student, template=self.student_template, issued_by=self.admin)
        staff_card = CardService.issue_staff_card(staff=self.staff, template=self.staff_template, issued_by=self.admin)
        self.assertRegex(student_card.card_number, r"^IDC-\d{4}-000001$")
        self.assertNotEqual(student_card.card_number, staff_card.card_number)
        self.assertEqual((student_card.holder_type, staff_card.holder_type), (HolderType.STUDENT, HolderType.STAFF))

    def test_xor_constraint_and_template_compatibility(self):
        with self.assertRaises(ValidationError):
            CardService.issue_student_card(student=self.student, template=self.staff_template)
        with self.assertRaises(IntegrityError), transaction.atomic():
            IDCard.objects.create(
                student=self.student, staff=self.staff, template=self.student_template, card_number="IDC-XOR"
            )

    def test_database_enforces_unique_card_number(self):
        CardService.issue_student_card(student=self.student, template=self.student_template)
        with self.assertRaises(IntegrityError), transaction.atomic():
            IDCard.objects.create(student=self.student, template=self.student_template, card_number="IDC-%s-000001" % __import__("datetime").date.today().year)

    def test_deactivation_preserves_history_and_records_reason(self):
        card = CardService.issue_student_card(student=self.student, template=self.student_template)
        CardService.deactivate_card(card, reason="Lost", revoke=True)
        self.assertEqual(card.status, IDCard.Status.REVOKED)
        self.assertEqual(card.deactivation_reason, "Lost")
        self.assertIsNotNone(card.deactivated_at)
        self.assertTrue(IDCard.objects.filter(pk=card.pk).exists())

    def test_only_one_active_card_per_holder(self):
        CardService.issue_student_card(student=self.student, template=self.student_template)
        CardService.issue_staff_card(staff=self.staff, template=self.staff_template)
        with self.assertRaises(ValidationError):
            CardService.issue_student_card(student=self.student, template=self.student_template)
        with self.assertRaises(ValidationError):
            CardService.issue_staff_card(staff=self.staff, template=self.staff_template)

    def test_replacement_retires_card_and_rfid_without_transferring_uid(self):
        old_card = CardService.issue_student_card(
            student=self.student, template=self.student_template, issued_by=self.admin
        )
        credential = RFIDCredentialService.assign(id_card=old_card, uid="AABBCCDD")
        replacement = CardService.replace_card(
            old_card, actor=self.admin, reason="Damaged"
        )
        old_card.refresh_from_db()
        credential.refresh_from_db()
        self.assertEqual(old_card.status, IDCard.Status.REPLACED)
        self.assertEqual(credential.status, RFIDCredential.Status.REPLACED)
        self.assertEqual(replacement.replaces_id, old_card.pk)
        self.assertEqual(replacement.replacement_reason, "Damaged")
        self.assertEqual(replacement.replaced_by, self.admin)
        self.assertFalse(replacement.rfid_credentials.exists())
        with self.assertRaises(ValidationError):
            RFIDCredentialService.assign(id_card=replacement, uid="AABBCCDD")

    def test_dynamic_student_staff_and_school_fields_resolve(self):
        student_card = CardService.issue_student_card(student=self.student, template=self.student_template)
        staff_card = CardService.issue_staff_card(staff=self.staff, template=self.staff_template)
        self.assertEqual(DynamicFieldRegistry.resolve(["student.full_name"], student_card)["student.full_name"], "Amina Bello")
        self.assertEqual(DynamicFieldRegistry.resolve(["staff.designation"], staff_card)["staff.designation"], "Bursar")
        branding = BrandingResolver.resolve()
        self.assertEqual(branding["name"], "SSync Academy")
        self.assertEqual(branding["motto"], "Learn and lead")
        self.assertEqual(DynamicFieldRegistry.resolve(["school.address"], student_card)["school.address"], "1 School Road")

    def test_unknown_resolution_is_rejected(self):
        card = CardService.issue_student_card(student=self.student, template=self.student_template)
        with self.assertRaises(ValidationError):
            DynamicFieldRegistry.resolve(["student.__dict__"], card)

    def _call(self, viewset, method, user=None, data=None, pk=None, action=None):
        request = getattr(self.factory, method)("/api/idcards/", data or {}, format="json")
        if user:
            force_authenticate(request, user=user)
        mapping = {method: action or ("create" if method == "post" else "list")}
        return viewset.as_view(mapping)(request, **({"pk": pk} if pk else {}))

    def test_permissions_reject_anonymous_and_teacher_and_allow_admin(self):
        payload = {"student": self.student.pk, "template": self.student_template.pk}
        self.assertEqual(self._call(IDCardViewSet, "post", data=payload).status_code, 401)
        self.assertEqual(self._call(IDCardViewSet, "post", self.teacher, payload).status_code, 403)
        self.assertEqual(self._call(IDCardViewSet, "post", self.admin, payload).status_code, 201)

    def test_template_api_create_and_activation_lifecycle(self):
        payload = {
            "name": "API Student", "holder_type": HolderType.STUDENT,
            "front_layout": layout("student.student_id", "dynamic_text"),
            "back_layout": {"schema_version": 1, "elements": []},
        }
        response = self._call(IDCardTemplateViewSet, "post", self.admin, payload)
        self.assertEqual(response.status_code, 201, response.data)
        response = self._call(IDCardTemplateViewSet, "post", self.admin, pk=response.data["id"], action="deactivate")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_active"])

    def test_field_registry_endpoint_is_filtered_and_admin_only(self):
        request = self.factory.get("/api/idcards/template-fields/?holder_type=STAFF")
        force_authenticate(request, user=self.admin)
        response = template_fields(request)
        self.assertEqual(response.status_code, 200)
        keys = {item["key"] for item in response.data}
        self.assertIn("staff.full_name", keys)
        self.assertNotIn("student.full_name", keys)

    def test_preview_context_resolves_only_fields_used_by_template(self):
        card = CardService.issue_student_card(student=self.student, template=self.student_template)
        context = CardService.prepare_card_context(card)
        self.assertEqual(set(context["values"]), {"student.full_name", "card.card_number"})
