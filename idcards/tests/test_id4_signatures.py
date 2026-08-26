from io import BytesIO
from PIL import Image

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from academic.models import Department, Staff, Student
from administration.models import AcademicYear, Term
from idcards.models import AuthorizedSignature, AuthorizedSignatureVersion, HolderType, IDCard, IDCardTemplate
from idcards.services import (
    AuthorizedSignatureService, CardService, IDCardRenderService,
    IDCardTemplateLifecycleService, LayoutValidator,
)
from idcards.views import AuthorizedSignatureViewSet
from school.testcases import TenantTestCase
from users.models import CustomUser


def _sample_signature_image(name="sig.png", format="PNG", size=(200, 80), color=(0, 0, 0, 255)):
    out = BytesIO()
    img = Image.new("RGBA" if format == "PNG" else "RGB", size, color)
    img.save(out, format=format)
    out.seek(0)
    mime = "image/png" if format == "PNG" else "image/jpeg"
    return SimpleUploadedFile(name, out.getvalue(), content_type=mime)


class ID4AuthorizedSignaturesTestCase(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.factory = APIRequestFactory()

        # Admin user
        self.admin_user = CustomUser.objects.create_superuser(
            email="admin_id4@test.com", password="password123", first_name="School", last_name="Admin",
        )
        self.admin_user.is_school_admin = True
        self.admin_user.save()

        # Teacher user
        self.teacher_user = CustomUser.objects.create_user(
            email="teacher_id4@test.com", password="password123", first_name="Tom", last_name="Teacher",
        )
        self.department = Department.objects.create(name="Mathematics")
        self.staff = Staff.objects.create(
            user=self.teacher_user, role=Staff.Role.TEACHER, designation="Math Teacher", department=self.department,
        )

        # Student user
        self.student_user = CustomUser.objects.create_user(
            email="student_id4@test.com", password="password123", first_name="Sam", last_name="Student",
        )
        self.student = Student.objects.create(
            user=self.student_user, first_name="Sam", last_name="Student", admission_number="ADM-ID4-001",
            date_of_birth="2009-01-01", gender="MALE", parent_contact="08099887766",
        )

        # Academic structure
        self.academic_year = AcademicYear.objects.create(
            name="2025/2026", start_date="2025-09-01", end_date="2026-07-31", active_year=True,
        )
        self.term = Term.objects.create(
            name="First Term", academic_year=self.academic_year, start_date="2025-09-01", end_date="2025-12-15",
        )

    def test_signature_creation_and_versioning_lifecycle(self):
        file1 = _sample_signature_image("principal_sig_v1.png")
        sig = AuthorizedSignatureService.create_signature(
            name="Principal Signature",
            signatory_name="Mrs. Amina Yusuf",
            signatory_title="Principal",
            description="Official primary principal signature",
            file=file1,
            user=self.admin_user,
        )

        self.assertEqual(sig.name, "Principal Signature")
        self.assertEqual(sig.signatory_name, "Mrs. Amina Yusuf")
        self.assertEqual(sig.signatory_title, "Principal")
        self.assertTrue(sig.is_active)
        self.assertIsNotNone(sig.current_version)
        self.assertEqual(sig.current_version.version_number, 1)
        self.assertEqual(sig.versions.count(), 1)

        # Replace signature image -> creates version 2
        file2 = _sample_signature_image("principal_sig_v2.png", size=(250, 90))
        v2 = AuthorizedSignatureService.replace_signature_image(sig, file=file2, user=self.admin_user)

        sig.refresh_from_db()
        self.assertEqual(v2.version_number, 2)
        self.assertEqual(sig.current_version_id, v2.id)
        self.assertEqual(sig.versions.count(), 2)

        # Verify version 1 is unchanged
        v1 = sig.versions.get(version_number=1)
        self.assertEqual(v1.version_number, 1)
        self.assertNotEqual(v1.id, v2.id)

        # Deactivate
        AuthorizedSignatureService.deactivate_signature(sig)
        sig.refresh_from_db()
        self.assertFalse(sig.is_active)

    def test_upload_security_and_validation(self):
        # SVG is rejected
        svg_file = SimpleUploadedFile("sig.svg", b"<svg><circle cx='10' cy='10' r='5'/></svg>", content_type="image/svg+xml")
        with self.assertRaises(ValidationError):
            AuthorizedSignatureService.create_signature(
                name="Bad SVG", signatory_name="Test", signatory_title="Admin", file=svg_file, user=self.admin_user,
            )

        # Non-image file is rejected
        text_file = SimpleUploadedFile("doc.txt", b"Hello World", content_type="text/plain")
        with self.assertRaises(ValidationError):
            AuthorizedSignatureService.create_signature(
                name="Bad Text", signatory_name="Test", signatory_title="Admin", file=text_file, user=self.admin_user,
            )

    def test_school_admin_permissions(self):
        view = AuthorizedSignatureViewSet.as_view({"get": "list", "post": "create"})

        # Teacher is denied access
        req_teacher = self.factory.get("/api/idcards/signatures/")
        force_authenticate(req_teacher, user=self.teacher_user)
        res_teacher = view(req_teacher)
        self.assertEqual(res_teacher.status_code, status.HTTP_403_FORBIDDEN)

        # Student is denied access
        req_student = self.factory.get("/api/idcards/signatures/")
        force_authenticate(req_student, user=self.student_user)
        res_student = view(req_student)
        self.assertEqual(res_student.status_code, status.HTTP_403_FORBIDDEN)

        # School Admin is permitted
        req_admin = self.factory.get("/api/idcards/signatures/")
        force_authenticate(req_admin, user=self.admin_user)
        res_admin = view(req_admin)
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)

    def test_template_layout_validation_with_signature(self):
        file_obj = _sample_signature_image()
        sig = AuthorizedSignatureService.create_signature(
            name="Registrar Signature", signatory_name="Mr. John Doe", signatory_title="Registrar",
            file=file_obj, user=self.admin_user,
        )
        v1 = sig.current_version

        # Valid signature element
        valid_layout = {
            "schema_version": 2,
            "coordinate_system": {"unit": "design_unit", "width": 10000, "height": 6306},
            "background": {"type": "color", "color": "#ffffff"},
            "safe_area": {"top": 250, "right": 250, "bottom": 250, "left": 250},
            "elements": [
                {
                    "id": "sig-01",
                    "type": "signature",
                    "signature_version_id": v1.id,
                    "x": 6000, "y": 4500, "width": 3000, "height": 1200,
                    "rotation": 0, "z_index": 1, "visible": True, "locked": False,
                    "show_signature_line": True, "show_signatory_name": True, "show_signatory_title": True,
                    "style": {"opacity": 1, "fit": "contain"}, "constraints": {},
                }
            ],
        }
        LayoutValidator.validate(valid_layout, HolderType.STUDENT, width_mm="85.60", height_mm="53.98", orientation="LANDSCAPE")

        # Invalid non-existent signature_version_id
        invalid_layout = {
            "schema_version": 2,
            "coordinate_system": {"unit": "design_unit", "width": 10000, "height": 6306},
            "background": {"type": "color", "color": "#ffffff"},
            "safe_area": {"top": 250, "right": 250, "bottom": 250, "left": 250},
            "elements": [
                {
                    "id": "sig-02",
                    "type": "signature",
                    "signature_version_id": 999999,
                    "x": 6000, "y": 4500, "width": 3000, "height": 1200,
                    "rotation": 0, "z_index": 1, "visible": True, "locked": False,
                    "style": {}, "constraints": {},
                }
            ],
        }
        with self.assertRaises(ValidationError):
            LayoutValidator.validate(invalid_layout, HolderType.STUDENT, width_mm="85.60", height_mm="53.98", orientation="LANDSCAPE")

    def test_historical_guarantee_and_rendering_immutability(self):
        # 1. Create signature with Version 1
        file1 = _sample_signature_image("sig1.png")
        sig = AuthorizedSignatureService.create_signature(
            name="Principal Signature", signatory_name="Mrs. Amina Yusuf", signatory_title="Principal",
            file=file1, user=self.admin_user,
        )
        v1 = sig.current_version

        # 2. Build template draft and publish V1 pinned to signature Version 1
        template = IDCardTemplateLifecycleService.create_template(
            name="Student ID Card with Sig", holder_type=HolderType.STUDENT, actor=self.admin_user,
        )
        draft = template.current_draft_version
        front_layout = {
            "schema_version": 2,
            "coordinate_system": {"unit": "design_unit", "width": 10000, "height": 6306},
            "background": {"type": "color", "color": "#ffffff"},
            "safe_area": {"top": 250, "right": 250, "bottom": 250, "left": 250},
            "elements": [
                {
                    "id": "sig-elem",
                    "type": "signature",
                    "signature_version_id": v1.id,
                    "x": 5500, "y": 4000, "width": 3500, "height": 1500,
                    "rotation": 0, "z_index": 1, "visible": True, "locked": False,
                    "show_signature_line": True, "show_signatory_name": True, "show_signatory_title": True,
                    "style": {"opacity": 1, "fit": "contain"}, "constraints": {},
                }
            ],
        }
        IDCardTemplateLifecycleService.update_draft(draft, front_layout=front_layout)
        published_v1 = IDCardTemplateLifecycleService.publish(draft, actor=self.admin_user)

        # 3. Issue card pinned to published_v1
        card = IDCard.objects.create(
            student=self.student, template=template, template_version=published_v1, card_number="IDC-SIG-001",
        )

        # 4. Render preview and PDF with Version 1
        preview_data_1 = IDCardRenderService.get_preview_data(card)
        self.assertIn(v1.id, preview_data_1["signatures"])
        self.assertEqual(preview_data_1["signatures"][v1.id]["signatory_name"], "Mrs. Amina Yusuf")

        pdf_1 = IDCardRenderService.generate_pdf(card)
        self.assertTrue(len(pdf_1) > 500)
        self.assertTrue(pdf_1.startswith(b"%PDF"))

        # 5. Replace signature with Version 2 (new image, e.g. new principal)
        file2 = _sample_signature_image("sig2.png")
        v2 = AuthorizedSignatureService.replace_signature_image(sig, file=file2, user=self.admin_user)

        # 6. Verify issued card STILL resolves and renders Version 1
        preview_data_after = IDCardRenderService.get_preview_data(card)
        # Template layout still references v1.id
        self.assertEqual(preview_data_after["front_layout"]["elements"][0]["signature_version_id"], v1.id)
        self.assertIn(v1.id, preview_data_after["signatures"])
        self.assertEqual(preview_data_after["signatures"][v1.id]["version_number"], 1)

        # 7. Verify deletion protection
        with self.assertRaises(ValidationError):
            AuthorizedSignatureService.delete_signature(sig)
