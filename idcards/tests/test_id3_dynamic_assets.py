from io import BytesIO
from PIL import Image

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from academic.models import Department, Staff, Student
from administration.models import AcademicYear, Term
from idcards.models import HolderType, IDCard, IDCardDesignAsset, IDCardTemplate, IDCardTemplateVersion
from idcards.services import (
    AcademicContextResolver, DynamicFieldRegistry, IconRegistry,
    IDCardAssetService, IDCardRenderService, IDCardTemplateLifecycleService,
)
from idcards.views import IDCardDesignAssetViewSet, template_fields
from school.testcases import TenantTestCase
from users.models import CustomUser


def _sample_image_file(name="sample.png", format="PNG", size=(100, 100), color=(255, 0, 0)):
    out = BytesIO()
    img = Image.new("RGBA" if format == "PNG" else "RGB", size, color)
    img.save(out, format=format)
    out.seek(0)
    mime = "image/png" if format == "PNG" else "image/jpeg"
    return SimpleUploadedFile(name, out.getvalue(), content_type=mime)


class ID3DynamicAndAssetsTestCase(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.factory = APIRequestFactory()
        self.admin_user = CustomUser.objects.create_superuser(
            email="admin_id3@test.com", password="password123", first_name="School", last_name="Admin",
        )
        self.admin_user.is_school_admin = True
        self.admin_user.save()

        self.student_user = CustomUser.objects.create_user(
            email="student_id3@test.com", password="password123", first_name="Alice", last_name="Johnson",
        )
        self.student = Student.objects.create(
            user=self.student_user, first_name="Alice", middle_name="Marie", last_name="Johnson",
            admission_number="ADM-2026-999", date_of_birth="2009-04-12", gender="FEMALE",
            parent_contact="08012345678",
        )

        self.staff_user = CustomUser.objects.create_user(
            email="staff_id3@test.com", password="password123", first_name="Arthur", last_name="Pendelton",
        )
        self.department = Department.objects.create(name="Humanities")
        self.staff = Staff.objects.create(
            user=self.staff_user, role=Staff.Role.TEACHER, designation="Head of History", department=self.department,
        )

        self.academic_year = AcademicYear.objects.create(
            name="2025/2026", start_date="2025-09-01", end_date="2026-07-31", active_year=True,
        )
        self.term = Term.objects.create(
            name="Term 1", academic_year=self.academic_year, start_date="2025-09-01", end_date="2025-12-15",
        )

    def test_dynamic_fields_metadata_and_availability(self):
        student_fields = DynamicFieldRegistry.available(HolderType.STUDENT)
        student_keys = {f["key"] for f in student_fields}
        self.assertIn("student.full_name", student_keys)
        self.assertIn("student.admission_number", student_keys)
        self.assertIn("student.middle_name", student_keys)
        self.assertIn("student.date_of_birth", student_keys)
        self.assertIn("academic.current_year", student_keys)
        self.assertIn("academic.current_term", student_keys)
        self.assertIn("card.card_number", student_keys)
        self.assertNotIn("staff.role", student_keys)
        self.assertNotIn("card.verification_token", student_keys)

        # Check metadata attributes
        fn_meta = next(f for f in student_fields if f["key"] == "student.full_name")
        self.assertEqual(fn_meta["group"], "student")
        self.assertEqual(fn_meta["type"], "text")
        self.assertTrue(fn_meta["example_value"])

    def test_canonical_academic_resolution(self):
        resolved = AcademicContextResolver.resolve()
        self.assertEqual(resolved["current_year"], "2025/2026")
        self.assertIn("Term", resolved["current_term"])

    def test_dynamic_field_resolution(self):
        template = IDCardTemplateLifecycleService.create_template(
            name="Student ID3 Test", holder_type=HolderType.STUDENT, actor=self.admin_user,
        )
        card = IDCard.objects.create(
            student=self.student, template=template, template_version=template.current_draft_version,
            card_number="IDC-ID3-001",
        )

        keys = [
            "student.full_name", "student.first_name", "student.middle_name",
            "student.last_name", "student.admission_number", "student.gender",
            "academic.current_year", "card.card_number",
        ]
        values = DynamicFieldRegistry.resolve(keys, card)
        self.assertEqual(values["student.full_name"], "Alice Marie Johnson")
        self.assertEqual(values["student.first_name"], "Alice")
        self.assertEqual(values["student.middle_name"], "Marie")
        self.assertEqual(values["student.last_name"], "Johnson")
        self.assertEqual(values["student.admission_number"], "ADM-2026-999")
        self.assertEqual(values["academic.current_year"], "2025/2026")
        self.assertEqual(values["card.card_number"], "IDC-ID3-001")

    def test_icon_registry_validation_and_rendering(self):
        self.assertTrue(IconRegistry.is_allowed("lucide:phone"))
        self.assertTrue(IconRegistry.is_allowed("lucide:school"))
        self.assertFalse(IconRegistry.is_allowed("arbitrary:evil-svg"))

        with self.assertRaises(ValidationError):
            IconRegistry.require("arbitrary:evil-svg")

        svg = IconRegistry.render_svg("lucide:phone", size=20, color="#2563eb", opacity=0.9)
        self.assertIn("<svg", svg)
        self.assertIn('stroke="#2563eb"', svg)
        self.assertIn("opacity: 0.9", svg)

    def test_asset_upload_and_validation(self):
        file_obj = _sample_image_file("crest.png", format="PNG", size=(200, 200))
        asset = IDCardAssetService.create_asset(
            file=file_obj, name="School Crest", asset_type=IDCardDesignAsset.AssetType.IMAGE, user=self.admin_user,
        )
        self.assertEqual(asset.name, "School Crest")
        self.assertEqual(asset.mime_type, "image/png")
        self.assertEqual(asset.width, 200)
        self.assertEqual(asset.height, 200)
        self.assertTrue(asset.is_active)
        self.assertTrue(asset.file.url)

    def test_asset_deletion_protection_when_referenced(self):
        file_obj = _sample_image_file("bg.jpg", format="JPEG", size=(300, 200))
        asset = IDCardAssetService.create_asset(
            file=file_obj, name="Card Background", asset_type=IDCardDesignAsset.AssetType.BACKGROUND, user=self.admin_user,
        )

        template = IDCardTemplateLifecycleService.create_template(
            name="Template With Asset", holder_type=HolderType.STUDENT, actor=self.admin_user,
        )
        draft = template.current_draft_version

        # Reference asset in front_layout background
        front_layout = {
            "schema_version": 2,
            "coordinate_system": {"unit": "design_unit", "width": 10000, "height": 6306},
            "background": {"type": "image", "asset_id": asset.id, "fit": "cover"},
            "safe_area": {"top": 250, "right": 250, "bottom": 250, "left": 250},
            "elements": [],
        }
        IDCardTemplateLifecycleService.update_draft(draft, front_layout=front_layout)

        # Asset is referenced -> delete must fail
        self.assertTrue(IDCardAssetService.is_asset_referenced(asset))
        with self.assertRaises(ValidationError):
            IDCardAssetService.delete_asset(asset)

        # Archiving is allowed
        IDCardAssetService.archive_asset(asset)
        asset.refresh_from_db()
        self.assertFalse(asset.is_active)

    def test_pdf_rendering_with_icons_and_assets(self):
        file_obj = _sample_image_file("logo.png", format="PNG", size=(100, 100))
        asset = IDCardAssetService.create_asset(
            file=file_obj, name="Emblem", asset_type=IDCardDesignAsset.AssetType.IMAGE, user=self.admin_user,
        )

        template = IDCardTemplateLifecycleService.create_template(
            name="Rich Student Card", holder_type=HolderType.STUDENT, actor=self.admin_user,
        )
        draft = template.current_draft_version
        front_layout = {
            "schema_version": 2,
            "coordinate_system": {"unit": "design_unit", "width": 10000, "height": 6306},
            "background": {"type": "color", "color": "#f8fafc"},
            "safe_area": {"top": 250, "right": 250, "bottom": 250, "left": 250},
            "elements": [
                {
                    "id": "icon-phone",
                    "type": "icon",
                    "icon": "lucide:phone",
                    "x": 500, "y": 500, "width": 500, "height": 500,
                    "rotation": 0, "z_index": 0, "visible": True, "locked": False,
                    "style": {"color": "#2563eb", "opacity": 1}, "constraints": {},
                },
                {
                    "id": "asset-img",
                    "type": "image",
                    "asset_id": asset.id,
                    "x": 1200, "y": 500, "width": 1500, "height": 1500,
                    "rotation": 0, "z_index": 1, "visible": True, "locked": False,
                    "style": {"fit": "contain", "opacity": 1}, "constraints": {},
                },
                {
                    "id": "dyn-name",
                    "type": "dynamic_text",
                    "x": 500, "y": 2500, "width": 5000, "height": 800,
                    "rotation": 0, "z_index": 2, "visible": True, "locked": False,
                    "binding": {"field": "student.full_name", "required": True, "hide_when_empty": False},
                    "style": {
                        "font_family": "Inter", "font_size": 22, "font_weight": 700,
                        "text_transform": "uppercase", "color": "#0f172a",
                    },
                    "constraints": {},
                },
                {
                    "id": "dyn-middle",
                    "type": "dynamic_text",
                    "x": 500, "y": 3500, "width": 5000, "height": 600,
                    "rotation": 0, "z_index": 3, "visible": True, "locked": False,
                    "binding": {"field": "student.middle_name", "required": False, "hide_when_empty": True},
                    "style": {"font_size": 16, "color": "#64748b"},
                    "constraints": {},
                },
            ],
        }
        IDCardTemplateLifecycleService.update_draft(draft, front_layout=front_layout)
        published = IDCardTemplateLifecycleService.publish(draft, actor=self.admin_user)

        card = IDCard.objects.create(
            student=self.student, template=template, template_version=published, card_number="IDC-RICH-001",
        )

        pdf_bytes = IDCardRenderService.generate_pdf(card)
        self.assertTrue(len(pdf_bytes) > 500)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
