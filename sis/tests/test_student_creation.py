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
from datetime import date, datetime, timedelta
from django.utils import timezone
from academic.services.student_creation_service import StudentCreationService

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

    def make_bulk_workbook(self, rows, headers=None):
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Students"
        sheet.append(headers or [
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

    def make_bulk_workbook_12(self, rows):
        headers = [
            "first_name", "middle_name", "last_name", "date_of_birth", "parent_contact",
            "parent_email", "parent_first_name", "parent_last_name",
            "religion", "classroom_id", "gender", "parent_address",
        ]
        return self.make_bulk_workbook(rows, headers=headers)

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
            "send_invitation": True,
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
            "send_invitation": True,
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
                "send_invitation": True,
            })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(UserInvitation.objects.filter(email=parent_user.email).exists())
        send_invitation.assert_not_called()

    @patch("core.email_utils.send_parent_invitation")
    def test_bulk_upload_valid_dob_iso_format(self, send_invitation):
        upload = self.make_bulk_workbook_12([
            ["Amina", "", "Bello", "2015-06-23", "08011112222", "amina.parent@test.com", "Musa", "Bello", "Islam", self.classroom.pk, "Female", "123 School Rd"],
        ])
        response = self.client.post("/api/sis/students/bulk-upload/", {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        student = Student.objects.get(first_name__iexact="Amina", last_name__iexact="Bello")
        self.assertEqual(student.date_of_birth, date(2015, 6, 23))

    @patch("core.email_utils.send_parent_invitation")
    def test_bulk_upload_valid_dob_dmy_slash_and_dash_formats(self, send_invitation):
        upload = self.make_bulk_workbook_12([
            ["Chidi", "", "Okoro", "23/06/2015", "08022223333", "chidi.parent@test.com", "Emeka", "Okoro", "Christian", self.classroom.pk, "Male", "456 Market St"],
            ["Ngozi", "", "Okoro", "23-06-2015", "08022223333", "chidi.parent@test.com", "Emeka", "Okoro", "Christian", self.classroom.pk, "Female", "456 Market St"],
        ])
        response = self.client.post("/api/sis/students/bulk-upload/", {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        chidi = Student.objects.get(first_name__iexact="Chidi")
        ngozi = Student.objects.get(first_name__iexact="Ngozi")
        self.assertEqual(chidi.date_of_birth, date(2015, 6, 23))
        self.assertEqual(ngozi.date_of_birth, date(2015, 6, 23))

    @patch("core.email_utils.send_parent_invitation")
    def test_bulk_upload_valid_dob_excel_date_cell(self, send_invitation):
        # Openpyxl cells can hold datetime objects directly
        upload = self.make_bulk_workbook_12([
            ["Zainab", "", "Aliyu", datetime(2016, 4, 15, 0, 0), "08033334444", "zainab.parent@test.com", "Aliyu", "Umar", "Islam", self.classroom.pk, "Female", ""],
        ])
        response = self.client.post("/api/sis/students/bulk-upload/", {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        student = Student.objects.get(first_name__iexact="Zainab")
        self.assertEqual(student.date_of_birth, date(2016, 4, 15))

    @patch("core.email_utils.send_parent_invitation")
    def test_bulk_upload_blank_dob_stores_none(self, send_invitation):
        upload = self.make_bulk_workbook_12([
            ["BlankDOB1", "", "Student", "", "08044445555", "blank1.parent@test.com", "John", "Doe", "Other", self.classroom.pk, "Male", ""],
            ["BlankDOB2", "", "Student", None, "08055556666", "blank2.parent@test.com", "Jane", "Doe", "Other", self.classroom.pk, "Female", ""],
            ["BlankDOB3", "", "Student", "   ", "08066667777", "blank3.parent@test.com", "Bob", "Doe", "Other", self.classroom.pk, "Male", ""],
        ])
        response = self.client.post("/api/sis/students/bulk-upload/", {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        s1 = Student.objects.get(first_name__iexact="BlankDOB1")
        s2 = Student.objects.get(first_name__iexact="BlankDOB2")
        s3 = Student.objects.get(first_name__iexact="BlankDOB3")
        self.assertIsNone(s1.date_of_birth)
        self.assertIsNone(s2.date_of_birth)
        self.assertIsNone(s3.date_of_birth)

    def test_bulk_upload_invalid_calendar_date_fails_prevalidation(self):
        upload = self.make_bulk_workbook_12([
            ["InvalidDay", "", "Student", "31/02/2015", "08077778888", "inv.parent@test.com", "Parent", "One", "Christian", self.classroom.pk, "Male", ""],
        ])
        response = self.client.post("/api/sis/students/bulk-upload/", {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(Student.objects.count(), 0)
        self.assertIn("date_of_birth must be a valid date", response.data["not_created"][0]["errors"][0])

    def test_bulk_upload_future_dob_fails_prevalidation(self):
        future_date = (timezone.now().date() + timedelta(days=365)).strftime("%Y-%m-%d")
        upload = self.make_bulk_workbook_12([
            ["Future", "", "Student", future_date, "08088889999", "future.parent@test.com", "Parent", "Two", "Christian", self.classroom.pk, "Female", ""],
        ])
        response = self.client.post("/api/sis/students/bulk-upload/", {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(Student.objects.count(), 0)
        self.assertIn("date_of_birth cannot be in the future", response.data["not_created"][0]["errors"][0])

    def test_bulk_upload_atomicity_with_invalid_dob(self):
        upload = self.make_bulk_workbook_12([
            ["ValidOne", "", "Student", "2015-01-10", "08099991111", "valid.parent@test.com", "Parent", "Three", "Christian", self.classroom.pk, "Male", ""],
            ["InvalidTwo", "", "Student", "2020-13-01", "08099992222", "inv.parent2@test.com", "Parent", "Four", "Christian", self.classroom.pk, "Female", ""],
        ])
        response = self.client.post("/api/sis/students/bulk-upload/", {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(Student.objects.count(), 0)
        self.assertEqual(len(response.data["not_created"]), 1)
        self.assertEqual(response.data["not_created"][0]["row"], 3)

    @patch("core.email_utils.send_parent_invitation")
    def test_bulk_upload_legacy_10_and_11_column_templates_supported(self, send_invitation):
        # Legacy 10-column without parent_address and without date_of_birth
        legacy_10 = self.make_bulk_workbook([
            ["LegacyTen", "", "Student", "08012345671", "legacy10@test.com", "LegParent", "Ten", "Christian", self.classroom.pk, "Male"],
        ])
        res10 = self.client.post("/api/sis/students/bulk-upload/", {"file": legacy_10}, format="multipart")
        self.assertEqual(res10.status_code, status.HTTP_201_CREATED, res10.data)
        s10 = Student.objects.get(first_name__iexact="LegacyTen")
        self.assertIsNone(s10.date_of_birth)

        # Legacy 11-column with parent_address but without date_of_birth
        headers_11 = [
            "first_name", "middle_name", "last_name", "parent_contact",
            "parent_email", "parent_first_name", "parent_last_name",
            "religion", "classroom_id", "gender", "parent_address",
        ]
        legacy_11 = self.make_bulk_workbook([
            ["LegacyEleven", "", "Student", "08012345672", "legacy11@test.com", "LegParent", "Eleven", "Christian", self.classroom.pk, "Female", "789 Old St"],
        ], headers=headers_11)
        res11 = self.client.post("/api/sis/students/bulk-upload/", {"file": legacy_11}, format="multipart")
        self.assertEqual(res11.status_code, status.HTTP_201_CREATED, res11.data)
        s11 = Student.objects.get(first_name__iexact="LegacyEleven")
        self.assertIsNone(s11.date_of_birth)

    def test_student_creation_service_persists_date_of_birth(self):
        student = StudentCreationService.create_student(
            classroom=self.classroom,
            first_name="ServiceDirect",
            last_name="Student",
            parent_phone="08033332222",
            parent_email="direct.service@test.com",
            parent_first_name="Direct",
            parent_last_name="Parent",
            date_of_birth=date(2014, 5, 10),
            send_invitation=False,
        )
        self.assertEqual(student.date_of_birth, date(2014, 5, 10))

    @patch("core.email_utils.send_parent_invitation")
    def test_create_student_without_parent_succeeds(self, send_invitation):
        data = {
            "first_name": "Amina",
            "last_name": "Ibrahim",
            "classroom_id": self.classroom.pk,
            "gender": "Female",
            "date_of_birth": "2016-05-04",
            "send_invitation": False,
        }
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.create_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        student = Student.objects.get(first_name__iexact="Amina", last_name__iexact="Ibrahim")
        self.assertIsNone(student.parent_guardian)
        self.assertIsNone(student.parent_contact)
        self.assertTrue(student.admission_number)
        self.assertTrue(StudentClassEnrollment.objects.filter(student=student, classroom=self.classroom).exists())
        self.assertEqual(Parent.objects.count(), 0)
        self.assertEqual(CustomUser.objects.filter(is_parent=True).count(), 0)
        self.assertEqual(UserInvitation.objects.count(), 0)
        send_invitation.assert_not_called()

    @patch("core.email_utils.send_parent_invitation")
    def test_create_student_with_parent_without_invitation(self, send_invitation):
        data = {
            "first_name": "Amina",
            "last_name": "Ibrahim",
            "classroom_id": self.classroom.pk,
            "parent_first_name": "Fatima",
            "parent_last_name": "Ibrahim",
            "parent_contact": "08031234567",
            "send_invitation": False,
        }
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.create_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        student = Student.objects.get(first_name__iexact="Amina", last_name__iexact="Ibrahim")
        self.assertIsNotNone(student.parent_guardian)
        self.assertEqual(student.parent_guardian.phone_number, "+2348031234567")
        self.assertIsNone(student.parent_guardian.email)
        self.assertIsNone(student.parent_guardian.user)
        self.assertEqual(UserInvitation.objects.count(), 0)
        send_invitation.assert_not_called()

    @patch("core.email_utils.send_parent_invitation")
    def test_create_student_with_parent_and_invitation(self, send_invitation):
        data = {
            "first_name": "Amina",
            "last_name": "Ibrahim",
            "classroom_id": self.classroom.pk,
            "parent_first_name": "Fatima",
            "parent_last_name": "Ibrahim",
            "parent_contact": "08031234567",
            "parent_email": "fatima@test.com",
            "send_invitation": True,
        }
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.create_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        student = Student.objects.get(first_name__iexact="Amina", last_name__iexact="Ibrahim")
        parent = Parent.objects.get(email="fatima@test.com")
        self.assertEqual(student.parent_guardian, parent)
        invitation = UserInvitation.objects.get(email="fatima@test.com", role="parent")
        self.assertEqual(invitation.parent_profile_id, parent.pk)
        send_invitation.assert_called_once_with(invitation)

    def test_send_invitation_requires_parent(self):
        data = {
            "first_name": "Amina",
            "last_name": "Ibrahim",
            "classroom_id": self.classroom.pk,
            "send_invitation": True,
        }
        response = self.client.post(self.create_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(Student.objects.count(), 0)
        self.assertTrue(
            "parent" in str(response.data).lower() or "guardian" in str(response.data).lower()
        )

    def test_send_invitation_requires_valid_parent_email(self):
        data = {
            "first_name": "Amina",
            "last_name": "Ibrahim",
            "classroom_id": self.classroom.pk,
            "parent_first_name": "Fatima",
            "parent_last_name": "Ibrahim",
            "parent_contact": "08031234567",
            "send_invitation": True,
        }
        response = self.client.post(self.create_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(Student.objects.count(), 0)
        self.assertTrue(
            "email" in str(response.data).lower()
        )

    @patch("core.email_utils.send_parent_invitation")
    def test_bulk_upload_without_parent_succeeds(self, send_invitation):
        upload = self.make_bulk_workbook_12([
            ["OrphanOne", "", "Student", "2016-01-01", "", "", "", "", "", self.classroom.pk, "Male", ""],
            ["OrphanTwo", "", "Student", "2016-02-02", "", "", "", "", "", self.classroom.pk, "Female", ""],
        ])
        response = self.client.post("/api/sis/students/bulk-upload/", {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(Student.objects.count(), 2)
        for student in Student.objects.all():
            self.assertIsNone(student.parent_guardian)
            self.assertIsNone(student.parent_contact)
            self.assertTrue(StudentClassEnrollment.objects.filter(student=student, classroom=self.classroom).exists())
        self.assertEqual(Parent.objects.count(), 0)
        self.assertEqual(UserInvitation.objects.count(), 0)
        send_invitation.assert_not_called()

    @patch("core.email_utils.send_parent_invitation")
    def test_bulk_upload_with_parent_does_not_send_invitation(self, send_invitation):
        upload = self.make_bulk_workbook_12([
            ["ChildWithParent", "", "Student", "2015-05-05", "08012345679", "parent.bulk@test.com", "Parent", "Bulk", "Christian", self.classroom.pk, "Male", "Address 1"],
        ])
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/sis/students/bulk-upload/", {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(Student.objects.count(), 1)
        student = Student.objects.first()
        self.assertIsNotNone(student.parent_guardian)
        self.assertEqual(student.parent_guardian.email, "parent.bulk@test.com")
        self.assertEqual(UserInvitation.objects.count(), 0)
        send_invitation.assert_not_called()

    @patch("core.email_utils.send_parent_invitation")
    def test_bulk_upload_mixed_batch_succeeds(self, send_invitation):
        upload = self.make_bulk_workbook_12([
            ["WithParent", "", "Student", "2015-01-01", "08011113333", "parent.mixed@test.com", "Parent", "Mixed", "Islam", self.classroom.pk, "Male", ""],
            ["WithoutParent", "", "Student", "2015-02-02", "", "", "", "", "", self.classroom.pk, "Female", ""],
        ])
        response = self.client.post("/api/sis/students/bulk-upload/", {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(Student.objects.count(), 2)
        with_p = Student.objects.get(first_name__iexact="WithParent")
        without_p = Student.objects.get(first_name__iexact="WithoutParent")
        self.assertIsNotNone(with_p.parent_guardian)
        self.assertIsNone(without_p.parent_guardian)
        send_invitation.assert_not_called()

    def test_service_create_student_without_parent(self):
        student = StudentCreationService.create_student(
            classroom=self.classroom,
            first_name="ServiceSolo",
            last_name="Student",
            send_invitation=False,
        )
        self.assertIsNone(student.parent_guardian)
        self.assertIsNone(student.parent_contact)
        self.assertTrue(StudentClassEnrollment.objects.filter(student=student, classroom=self.classroom).exists())

    @patch("core.email_utils.send_parent_invitation")
    def test_existing_parent_without_user_can_gain_email_and_receive_invitation(self, send_invitation):
        # 1. Create first student with guardian having phone and name, but no email
        data1 = {
            "first_name": "FirstChild",
            "last_name": "Bello",
            "classroom_id": self.classroom.pk,
            "parent_first_name": "Usman",
            "parent_last_name": "Bello",
            "parent_contact": "08035556666",
            "send_invitation": False,
        }
        with self.captureOnCommitCallbacks(execute=True):
            res1 = self.client.post(self.create_url, data1)
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED, res1.data)

        # 2. Assert: one Parent exists, user is None, email is None, student linked
        self.assertEqual(Parent.objects.count(), 1)
        parent = Parent.objects.first()
        self.assertIsNone(parent.user)
        self.assertIsNone(parent.email)
        self.assertEqual(parent.phone_number, "+2348035556666")
        student1 = Student.objects.get(first_name__iexact="FirstChild")
        self.assertEqual(student1.parent_guardian, parent)
        self.assertEqual(UserInvitation.objects.count(), 0)
        send_invitation.assert_not_called()

        # 3. Later the school obtains the parent's email and enrolls a second student (sibling)
        # providing the same phone, the new email, and opting in for an invitation
        data2 = {
            "first_name": "SecondChild",
            "last_name": "Bello",
            "classroom_id": self.classroom.pk,
            "parent_first_name": "Usman",
            "parent_last_name": "Bello",
            "parent_contact": "+2348035556666",
            "parent_email": "usman.bello@example.com",
            "send_invitation": True,
        }
        with self.captureOnCommitCallbacks(execute=True):
            res2 = self.client.post(self.create_url, data2)
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED, res2.data)

        # 4. Assert: the same Parent row is reused, CustomUser is attached, email is correct
        self.assertEqual(Parent.objects.count(), 1)
        parent.refresh_from_db()
        self.assertEqual(parent.email, "usman.bello@example.com")
        self.assertIsNotNone(parent.user)
        self.assertEqual(parent.user.email, "usman.bello@example.com")
        self.assertEqual(parent.user.phone_number, "+2348035556666")
        self.assertTrue(parent.user.is_parent)
        self.assertNotIn("ssyncportal.local", parent.user.email)

        # 5. Assert: both students share the same parent
        student2 = Student.objects.get(first_name__iexact="SecondChild")
        self.assertEqual(student2.parent_guardian, parent)
        self.assertEqual(student1.parent_guardian, student2.parent_guardian)

        # 6. Assert: invitation was created and dispatched after commit
        self.assertEqual(UserInvitation.objects.count(), 1)
        invitation = UserInvitation.objects.get(email="usman.bello@example.com")
        self.assertEqual(invitation.parent_profile_id, parent.pk)
        send_invitation.assert_called_once_with(invitation)

    def test_existing_parent_rejects_email_belonging_to_different_user_or_parent(self):
        # Create Parent A with phone only (no email, no user)
        parent_a = Parent.objects.create(
            phone_number="+2348011112222",
            first_name="Parent",
            last_name="Alpha",
        )

        # Create a completely separate User B / Parent B with email "different.user@test.com"
        user_b = CustomUser.objects.create_user(
            email="different.user@test.com",
            password="password123",
            phone_number="+2348099998888",
            is_parent=True,
        )
        Parent.objects.create(
            user=user_b,
            phone_number=user_b.phone_number,
            email=user_b.email,
            first_name="Parent",
            last_name="Beta",
        )

        # Attempt to link Parent A's phone (+2348011112222) with User B's email (different.user@test.com)
        data = {
            "first_name": "ConflictChild",
            "last_name": "Student",
            "classroom_id": self.classroom.pk,
            "parent_first_name": "Parent",
            "parent_last_name": "Alpha",
            "parent_contact": "+2348011112222",
            "parent_email": "different.user@test.com",
            "send_invitation": False,
        }
        response = self.client.post(self.create_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertTrue(
            "different" in str(response.data).lower() or "conflict" in str(response.data).lower()
        )

        # Confirm Parent A was not mutated or merged
        parent_a.refresh_from_db()
        self.assertIsNone(parent_a.user)
        self.assertIsNone(parent_a.email)
        self.assertEqual(Parent.objects.count(), 2)



