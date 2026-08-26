from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from academic.models import Student
from idcards.models import HolderType, IDCardTemplate
from idcards.services import CardService, IDCardTemplateLifecycleService, LayoutService
from idcards.views import IDCardViewSet
from school.testcases import TenantTestCase

User = get_user_model()


def make_layout_v2(text):
    layout = LayoutService.empty_v2("85.60", "53.98", "LANDSCAPE")
    layout["elements"] = [
        {
            "id": "name-field",
            "type": "dynamic_text",
            "x": 1000,
            "y": 1000,
            "width": 5000,
            "height": 800,
            "rotation": 0,
            "z_index": 0,
            "visible": True,
            "locked": False,
            "style": {"font_size": 24, "color": "#111827", "font_weight": "bold"},
            "constraints": {},
            "binding": {"field": "student.full_name", "required": True, "hide_when_empty": False},
        },
        {
            "id": "label-static",
            "type": "text",
            "text": text,
            "x": 1000,
            "y": 2000,
            "width": 5000,
            "height": 600,
            "rotation": 0,
            "z_index": 1,
            "visible": True,
            "locked": False,
            "style": {"font_size": 18, "color": "#4b5563"},
            "constraints": {},
        },
        {
            "id": "card-num-field",
            "type": "dynamic_text",
            "x": 1000,
            "y": 3000,
            "width": 5000,
            "height": 600,
            "rotation": 0,
            "z_index": 2,
            "visible": True,
            "locked": False,
            "style": {"font_size": 14, "color": "#4b5563"},
            "constraints": {},
            "binding": {"field": "card.card_number", "required": False, "hide_when_empty": False},
        },
    ]
    return layout


class IDCardPreviewAndPrintTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.name = "Preview Academy"
        tenant.motto = "Learn and lead"
        tenant.address = "1 School Road"
        tenant.contact_phone = "08000000000"
        tenant.contact_email = "hello@ssync.test"
        return super().setup_tenant(tenant)

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(
            email="admin@preview.edu",
            password="password123",
            is_admin=True,
            is_staff=True,
        )
        self.factory = APIRequestFactory()

        self.student = Student.objects.create(
            first_name="Ada",
            last_name="Lovelace",
            admission_number="ADM-2026-001",
            parent_contact="08012345678",
        )

        self.template = IDCardTemplateLifecycleService.create_template(
            name="Student ID Card",
            holder_type=HolderType.STUDENT,
            actor=self.admin,
            front_layout=make_layout_v2("Version 1 Badge"),
            back_layout=make_layout_v2("Version 1 Back"),
        )
        self.v1 = IDCardTemplateLifecycleService.publish(
            self.template.current_draft_version, actor=self.admin
        )
        self.card = CardService.issue_student_card(
            student=self.student, template=self.template, issued_by=self.admin
        )

    def _call(self, action_name, pk, query_params=None):
        url = f"/api/idcards/cards/{pk}/{action_name}/"
        if query_params:
            url += f"?{query_params}"
        request = self.factory.get(url)
        force_authenticate(request, user=self.admin)
        view = IDCardViewSet.as_view({"get": action_name})
        return view(request, pk=pk)

    def test_preview_endpoint_returns_resolved_card_and_holder_data(self):
        response = self._call("preview", self.card.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        self.assertEqual(data["card"]["id"], self.card.id)
        self.assertEqual(data["card"]["card_number"], self.card.card_number)
        self.assertEqual(data["card"]["holder_type"], "STUDENT")

        self.assertEqual(data["holder"]["name"], "Ada Lovelace")
        self.assertEqual(data["holder"]["identifier"], "ADM-2026-001")
        self.assertEqual(data["holder"]["context"], "")

        self.assertEqual(data["template_version"]["id"], self.v1.id)
        self.assertEqual(data["template_version"]["version_number"], 1)

        self.assertEqual(data["values"]["student.full_name"], "Ada Lovelace")
        self.assertEqual(data["values"]["card.card_number"], self.card.card_number)

    def test_print_endpoint_generates_pdf(self):
        response = self._call("print_card", self.card.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("inline", response["Content-Disposition"])
        self.assertIn(f"id-card-{self.card.card_number}.pdf", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF-"))

    def test_print_endpoint_download_disposition(self):
        response = self._call("print_card", self.card.pk, query_params="download=true")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])

    def test_card_pinned_to_v1_still_previews_and_prints_v1_after_v2_published(self):
        # Create V2 draft with different layout and publish it
        draft_v2 = IDCardTemplateLifecycleService.create_draft(self.template, actor=self.admin)
        IDCardTemplateLifecycleService.update_draft(
            draft_v2,
            front_layout=make_layout_v2("Version 2 Redesign"),
            back_layout=make_layout_v2("Version 2 Back"),
        )
        v2 = IDCardTemplateLifecycleService.publish(draft_v2, actor=self.admin)

        # Student 2 issued on newly published V2
        student2 = Student.objects.create(
            first_name="Grace",
            last_name="Hopper",
            admission_number="ADM-2026-002",
            parent_contact="08012345679",
        )
        card_v2 = CardService.issue_student_card(
            student=student2, template=self.template, issued_by=self.admin
        )

        # Card 1 (pinned to V1) preview check
        res_v1 = self._call("preview", self.card.pk).data
        self.assertEqual(res_v1["template_version"]["id"], self.v1.id)
        self.assertEqual(res_v1["template_version"]["version_number"], 1)
        self.assertEqual(res_v1["front_layout"]["elements"][1]["text"], "Version 1 Badge")

        # Card 2 (pinned to V2) preview check
        res_v2 = self._call("preview", card_v2.pk).data
        self.assertEqual(res_v2["template_version"]["id"], v2.id)
        self.assertEqual(res_v2["template_version"]["version_number"], 2)
        self.assertEqual(res_v2["front_layout"]["elements"][1]["text"], "Version 2 Redesign")

        # PDF print responses for both cards succeed
        print_v1 = self._call("print_card", self.card.pk)
        self.assertEqual(print_v1.status_code, status.HTTP_200_OK)
        self.assertTrue(print_v1.content.startswith(b"%PDF-"))

        print_v2 = self._call("print_card", card_v2.pk)
        self.assertEqual(print_v2.status_code, status.HTTP_200_OK)
        self.assertTrue(print_v2.content.startswith(b"%PDF-"))
