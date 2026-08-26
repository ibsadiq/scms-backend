from unittest.mock import patch

from django.core.exceptions import ValidationError
from school.testcases import TenantTestCase

from academic.models import (
    AdmissionStatus, ClassRoom, GradeLevel, Parent, Student,
    StudentClassEnrollment,
)
from academic.services.admission_enrollment_service import AdmissionEnrollmentService
from academic.tests.admissions_support import make_admissions_structure, make_application
from users.models import CustomUser


class AdmissionEnrollmentTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True

    def setUp(self):
        self.year, self.grade, self.classroom, self.session = make_admissions_structure()
        self.actor = CustomUser.objects.create_user(
            email="admin@enrollment.test", password="x", is_admin=True,
        )

    @patch("core.email_utils.send_parent_invitation")
    def test_accepted_application_converts_atomically(self, send_invitation):
        application = make_application(self.session, self.grade, status=AdmissionStatus.ACCEPTED)
        with self.captureOnCommitCallbacks(execute=True):
            student = AdmissionEnrollmentService.enroll(
                application=application, classroom=self.classroom, actor=self.actor,
            )
        application.refresh_from_db()
        student.refresh_from_db()
        self.classroom.refresh_from_db()
        self.assertEqual(application.enrolled_student, student)
        self.assertEqual(application.status, AdmissionStatus.ENROLLED)
        self.assertRegex(student.admission_number, r"^ADM-\d{4}-\d{4,}$")
        self.assertEqual(student.parent_contact, application.parent_phone)
        self.assertEqual(student.parent_guardian.phone_number, application.parent_phone)
        self.assertFalse(student.can_login)
        self.assertEqual(student.classroom, self.classroom)
        self.assertEqual(self.classroom.occupied_sits, 1)
        self.assertEqual(StudentClassEnrollment.objects.filter(student=student, is_active=True).count(), 1)
        self.assertTrue(student.parent_guardian.user.has_usable_password() is False)
        send_invitation.assert_called_once()

    def test_invalid_states_and_repeat_conversion_are_rejected(self):
        for state in (
            AdmissionStatus.DRAFT, AdmissionStatus.SUBMITTED,
            AdmissionStatus.UNDER_REVIEW, AdmissionStatus.REJECTED,
            AdmissionStatus.WITHDRAWN,
        ):
            application = make_application(self.session, self.grade, suffix=state, status=state)
            with self.assertRaises(ValidationError):
                AdmissionEnrollmentService.enroll(
                    application=application, classroom=self.classroom, actor=self.actor,
                )
        accepted = make_application(self.session, self.grade, suffix="accepted", status=AdmissionStatus.ACCEPTED)
        AdmissionEnrollmentService.enroll(
            application=accepted, classroom=self.classroom, actor=self.actor,
        )
        with self.assertRaises(ValidationError):
            AdmissionEnrollmentService.enroll(
                application=accepted, classroom=self.classroom, actor=self.actor,
            )

    def test_full_classroom_rolls_back_conversion_and_retry_succeeds(self):
        application = make_application(self.session, self.grade, status=AdmissionStatus.ACCEPTED)
        self.classroom.occupied_sits = self.classroom.capacity
        self.classroom.save(update_fields=("occupied_sits",))
        before = (Student.objects.count(), Parent.objects.count(), CustomUser.objects.count())
        with self.assertRaises(ValidationError):
            AdmissionEnrollmentService.enroll(
                application=application, classroom=self.classroom, actor=self.actor,
            )
        application.refresh_from_db()
        self.classroom.refresh_from_db()
        self.assertEqual((Student.objects.count(), Parent.objects.count(), CustomUser.objects.count()), before)
        self.assertIsNone(application.enrolled_student)
        self.assertEqual(application.status, AdmissionStatus.ACCEPTED)
        self.assertEqual(self.classroom.occupied_sits, self.classroom.capacity)

        self.classroom.occupied_sits = 0
        self.classroom.save(update_fields=("occupied_sits",))
        student = AdmissionEnrollmentService.enroll(
            application=application, classroom=self.classroom, actor=self.actor,
        )
        self.assertIsNotNone(student.pk)

    def test_wrong_grade_classroom_leaves_application_unchanged(self):
        other_grade = GradeLevel.objects.create(
            system_code="JSS_2", section="JSS", default_name="JSS 2", sequence_order=12,
        )
        other_room = ClassRoom.objects.create(name="JSS 2 Other", grade_level=other_grade)
        application = make_application(self.session, self.grade, status=AdmissionStatus.ACCEPTED)
        with self.assertRaises(ValidationError):
            AdmissionEnrollmentService.enroll(
                application=application, classroom=other_room, actor=self.actor,
            )
        application.refresh_from_db()
        self.assertIsNone(application.enrolled_student)
        self.assertFalse(Student.objects.exists())
