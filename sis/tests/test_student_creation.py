from unittest.mock import patch
from io import BytesIO

import openpyxl
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from academic.models import (
    ClassRoom,
    GradeLevel,
    NumberResetPolicy,
    Parent,
    Student,
    StudentAdmissionNumberPolicy,
    StudentClassEnrollment,
)
from academic.services.parent_identity_service import ParentIdentityService
from academic.models.choices import StandardClassCode, SectionType
from administration.models import AcademicYear, Term
from users.models import CustomUser, UserInvitation
from school.testcases import TenantTestCase
from datetime import date

@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class StudentCreationTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.status = "active"
        return super().setup_tenant(tenant)

    def setUp(self):
        super().setUp()
        self.client = APIClient(HTTP_HOST=self.domain.domain)

        # Admin user
        self.admin = CustomUser.objects.create_user(
            email="admin@test.com", password="password", is_admin=True, phone_number="12345678"
        )
        self.client.force_authenticate(user=self.admin)
        self.academic_year = AcademicYear.objects.create(
            name="2026/2027", 
            active_year=True,
            start_date=date(2026, 9, 1),
            end_date=date(2027, 7, 31)
        )
        self.term = Term.objects.create(
            name="First Term", 
            academic_year=self.academic_year,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 15)
        )

        self.grade_level = GradeLevel.objects.create(
            system_code=StandardClassCode.JSS_1,
            section=SectionType.JUNIOR_SECONDARY,
            default_name="JSS 1",
            sequence_order=7,
            alias="JSS 1"
        )
        self.classroom = ClassRoom.objects.create(name="A", grade_level=self.grade_level, capacity=30, occupied_sits=0)
        StudentAdmissionNumberPolicy.objects.create(
            pattern="{PREFIX}-{SEQ}",
            prefix="STU",
            sequence_width=6,
            reset_policy=NumberResetPolicy.NEVER,
        )

        self.create_url = "/api/sis/students/"

    def make_bulk_workbook(self, rows):
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Students"
        sheet.append([
            "first_name", "middle_name", "last_name", "parent_contact",
            "parent_email", "parent_first_name", "parent_last_name",
            "religion", "classroom_id", "gender",
        ])
        for row in rows:
            sheet.append(row)
        content = BytesIO()
        workbook.save(content)
        content.seek(0)
        return SimpleUploadedFile(
            "students.xlsx", content.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_bulk_upload_rejects_entire_file_before_creating_any_students(self):
        upload = self.make_bulk_workbook([
            ["Valid", "", "Student", "08012345678", "valid@test.com", "Valid", "Parent", "Christian", self.classroom.pk, "Male"],
            ["Bad", "", "Student", "A STREET ADDRESS", "bad@test.com", "Bad", "Parent", "Christian", self.classroom.pk, "Female"],
        ])
        response = self.client.post("/api/sis/students/bulk-upload/", {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(Student.objects.count(), 0)
        self.assertEqual(response.data["not_created"][0]["row"], 3)
        self.assertIn("valid phone number", response.data["not_created"][0]["errors"][0])

    @patch("core.email_utils.send_parent_invitation")
    def test_bulk_upload_assigns_siblings_to_one_canonical_parent(self, send_invitation):
        upload = self.make_bulk_workbook([
            ["First", "", "Child", "08012345678", "family@test.com", "Shared", "Parent", "Christian", self.classroom.pk, "Male"],
            ["Second", "", "Child", "+2348012345678", "family@test.com", "Shared", "Parent", "Christian", self.classroom.pk, "Female"],
        ])
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/sis/students/bulk-upload/", {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        students = list(Student.objects.order_by("pk"))
        self.assertEqual(len(students), 2)
        self.assertEqual(students[0].parent_guardian, students[1].parent_guardian)
        self.assertEqual(students[0].parent_contact, "+2348012345678")
        self.assertEqual(students[1].parent_contact, "+2348012345678")

    @patch("core.email_utils.send_parent_invitation")
    def test_direct_create_creates_student_enrollment_and_parent_invitation(self, send_invitation):
        data = {
            "first_name": "Test",
            "last_name": "Student",
            "classroom_id": self.classroom.pk,
            "parent_contact": "08012345678",
            "phone_number": "08099990001",
            "parent_email": "parent@test.com",
            "parent_first_name": "John",
            "parent_last_name": "Doe",
        }
        
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.create_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        # Check student
        student = Student.objects.get(first_name__iexact="Test")
        self.assertEqual(student.classroom, self.classroom)
        self.assertTrue(student.admission_number) # Allocated automatically
        self.assertEqual(student.phone_number, "08099990001")

        # Check parent
        parent = Parent.objects.get(phone_number="+2348012345678")
        self.assertEqual(parent.email, "parent@test.com")
        self.assertEqual(student.parent_guardian, parent)
        self.assertEqual(student.parent_contact, parent.phone_number)
        invitation = UserInvitation.objects.get(
            email=parent.email, role="parent", status="pending"
        )
        self.assertEqual(invitation.parent_profile_id, parent.pk)
        self.assertEqual(invitation.invited_by, self.admin)
        send_invitation.assert_called_once_with(invitation)

        # Check enrollment
        enrollment = StudentClassEnrollment.objects.get(student=student)
        self.assertEqual(enrollment.classroom, self.classroom)
        self.assertEqual(enrollment.academic_year, self.academic_year)
        
        # Capacity check
        self.classroom.refresh_from_db()
        self.assertEqual(self.classroom.occupied_sits, 1)

    def test_direct_create_requires_classroom(self):
        data = {
            "first_name": "Test",
            "last_name": "Student",
            # missing classroom_id
        }
        response = self.client.post(self.create_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("classroom_id", response.data.get("detail", response.data))

    def test_update_parent_assignment_synchronizes_guardian_and_contact(self):
        student = Student.objects.create(
            first_name="Editable", last_name="Student", admission_number="EDIT-1",
        )
        response = self.client.patch(
            f"/api/sis/students/{student.pk}/",
            {
                "parent_contact": "08033334444",
                "parent_email": "edited-parent@test.com",
                "parent_first_name": "Edited",
                "parent_last_name": "Parent",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        student.refresh_from_db()
        self.assertEqual(student.parent_contact, "+2348033334444")
        self.assertEqual(student.parent_guardian.phone_number, student.parent_contact)

    def test_update_can_temporarily_unlink_parent(self):
        parent = ParentIdentityService.resolve_parent(
            phone_number="08044445555", email="unlink@test.com",
        )
        student = Student.objects.create(
            first_name="Unlink", last_name="Student", admission_number="EDIT-2",
            parent_guardian=parent, parent_contact=parent.phone_number,
        )
        response = self.client.patch(
            f"/api/sis/students/{student.pk}/",
            {"parent_contact": "", "parent_email": ""},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        student.refresh_from_db()
        self.assertIsNone(student.parent_guardian)
        self.assertIsNone(student.parent_contact)

    def test_mismatch_class_level_and_classroom_rejected(self):
        data = {
            "first_name": "Test",
            "last_name": "Student",
            "classroom_id": self.classroom.pk,
            "class_level": "JSS 2", # Mismatch! classroom is JSS 1
            "parent_contact": "08012345678",
            "parent_email": "parent@test.com",
        }
        response = self.client.post(self.create_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_explicit_admission_number_is_ignored(self):
        data = {
            "first_name": "Legacy",
            "last_name": "Student",
            "classroom_id": self.classroom.pk,
            "admission_number": "LEGACY-001",
            "parent_contact": "08012345678",
            "parent_email": "parent@test.com",
        }
        response = self.client.post(self.create_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        student = Student.objects.get(first_name__iexact="Legacy")
        self.assertNotEqual(student.admission_number, "LEGACY-001")
        self.assertTrue(student.admission_number)

    def test_rollback_on_capacity_failure(self):
        self.classroom.capacity = 0
        self.classroom.save()

        data = {
            "first_name": "Failed",
            "last_name": "Student",
            "classroom_id": self.classroom.pk,
            "parent_contact": "08012345679",
            "parent_email": "parent2@test.com",
        }
        response = self.client.post(self.create_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Rollback check
        self.assertFalse(Student.objects.filter(first_name="Failed").exists())
        self.assertFalse(Parent.objects.filter(email="parent2@test.com").exists())

    @patch("core.email_utils.send_parent_invitation")
    def test_sibling_creation_does_not_duplicate_pending_parent_invitation(self, send_invitation):
        base_data = {
            "last_name": "Student",
            "classroom_id": self.classroom.pk,
            "parent_contact": "08012345670",
            "parent_email": "shared-parent@test.com",
            "parent_first_name": "Shared",
            "parent_last_name": "Parent",
        }

        with self.captureOnCommitCallbacks(execute=True):
            first_response = self.client.post(
                self.create_url, {**base_data, "first_name": "First"}
            )
        with self.captureOnCommitCallbacks(execute=True):
            second_response = self.client.post(
                self.create_url, {**base_data, "first_name": "Second"}
            )

        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            UserInvitation.objects.filter(
                email="shared-parent@test.com", role="parent", status="pending"
            ).count(),
            1,
        )
        send_invitation.assert_called_once()

    @patch("core.email_utils.send_parent_invitation")
    def test_active_existing_parent_is_not_reinvited(self, send_invitation):
        parent_user = CustomUser.objects.create_user(
            email="active-parent@test.com",
            password="existing-password",
            phone_number="08012345671",
            is_parent=True,
        )
        Parent.objects.create(
            user=parent_user,
            first_name="Active",
            last_name="Parent",
            email=parent_user.email,
            phone_number=parent_user.phone_number,
        )

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.create_url, {
                "first_name": "Third",
                "last_name": "Student",
                "classroom_id": self.classroom.pk,
                "parent_contact": parent_user.phone_number,
                "parent_email": parent_user.email,
                "parent_first_name": "Active",
                "parent_last_name": "Parent",
            })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(UserInvitation.objects.filter(email=parent_user.email).exists())
        send_invitation.assert_not_called()
