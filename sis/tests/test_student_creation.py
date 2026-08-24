from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from academic.models import ClassRoom, ClassLevel, Student, Parent, StudentClassEnrollment, GradeLevel
from academic.models.choices import StandardClassCode, SectionType
from administration.models import AcademicYear, Term
from users.models import CustomUser, UserInvitation
from school.testcases import TenantTestCase
from datetime import date

@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class StudentCreationTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

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
        self.class_level = ClassLevel.objects.create(name="JSS 1", grade_level=self.grade_level)
        self.classroom = ClassRoom.objects.create(name=self.class_level, capacity=30, occupied_sits=0)

        self.create_url = "/api/sis/students/"

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
        student = Student.objects.get(first_name="Test")
        self.assertEqual(student.class_level, self.class_level)
        self.assertTrue(student.admission_number) # Allocated automatically
        self.assertEqual(student.phone_number, "08099990001")

        # Check parent
        parent = Parent.objects.get(phone_number="08012345678")
        self.assertEqual(parent.email, "parent@test.com")
        self.assertEqual(student.parent_guardian, parent)
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
        self.assertIn("classroom_id", response.data)

    def test_mismatch_class_level_and_classroom_rejected(self):
        other_grade = GradeLevel.objects.create(name="Grade 8", alias="JSS 2", rank=8)
        other_level = ClassLevel.objects.create(name="JSS 2", grade_level=other_grade)
        
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
        
        student = Student.objects.get(first_name="Legacy")
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
