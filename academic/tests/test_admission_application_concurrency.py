from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import connections
from django_tenants.utils import schema_context

from academic.models import (
    AdmissionApplication, AdmissionApplicationNumberPolicy, AdmissionStatus,
    NumberResetPolicy, Student, StudentAdmissionNumberPolicy,
    StudentClassEnrollment,
)
from academic.services.admission_enrollment_service import AdmissionEnrollmentService
from academic.tests.admissions_support import make_admissions_structure, make_application
from school.testcases import TenantTransactionTestCase
from tenants.models import TenantStatus
from users.models import CustomUser


class AdmissionApplicationConcurrencyTests(TenantTransactionTestCase):

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = "Admissions Concurrency School"
        tenant.status = TenantStatus.ACTIVE

    def setUp(self):
        self.year, self.grade, self.classroom, self.session = make_admissions_structure()
        AdmissionApplicationNumberPolicy.objects.create(
            pattern="{PREFIX}/{YEAR2}/{SEQ}", prefix="APP", sequence_width=5,
            reset_policy=NumberResetPolicy.ACADEMIC_YEAR,
        )
        StudentAdmissionNumberPolicy.objects.create(
            pattern="{PREFIX}-{SEQ}", prefix="STU", sequence_width=6,
            reset_policy=NumberResetPolicy.NEVER,
        )

    def _create_application(self, index, barrier):
        connections.close_all()
        try:
            with schema_context(self.tenant.schema_name):
                session = type(self.session).objects.get(pk=self.session.pk)
                grade = type(self.grade).objects.get(pk=self.grade.pk)
                barrier.wait()
                application = make_application(
                    session, grade, suffix=f"concurrent-{index}",
                    status=AdmissionStatus.SUBMITTED,
                )
                return application.application_number
        finally:
            connections.close_all()

    def test_concurrent_submissions_receive_distinct_application_numbers(self):
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            numbers = list(executor.map(
                lambda index: self._create_application(index, barrier), range(2)
            ))
        self.assertEqual(len(set(numbers)), 2)
        self.assertEqual(
            AdmissionApplication.objects.filter(application_number__in=numbers).count(), 2
        )
        self.assertTrue(all(number.startswith("APP/35/") for number in numbers))

    def _create_student(self, index, barrier):
        connections.close_all()
        try:
            with schema_context(self.tenant.schema_name):
                barrier.wait()
                student = Student.objects.create(
                    first_name=f"Concurrent {index}", last_name="Student",
                    parent_contact=f"0808000000{index}",
                )
                return student.admission_number
        finally:
            connections.close_all()

    def test_concurrent_students_remain_unique_under_custom_policy(self):
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            numbers = list(executor.map(
                lambda index: self._create_student(index, barrier), range(2)
            ))
        self.assertEqual(len(set(numbers)), 2)
        self.assertTrue(all(number.startswith("STU-") for number in numbers))

    def test_deleted_application_number_is_not_reused(self):
        first = make_application(self.session, self.grade, suffix="deleted")
        first_number = first.application_number
        first.delete()
        second = make_application(self.session, self.grade, suffix="after-delete")
        self.assertNotEqual(second.application_number, first_number)


class AdmissionEnrollmentConcurrencyTests(TenantTransactionTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = "Admissions Enrollment Concurrency School"
        tenant.status = TenantStatus.ACTIVE

    def setUp(self):
        self.year, self.grade, self.classroom, self.session = make_admissions_structure()
        self.actor = CustomUser.objects.create_user(
            email="admin@enrollment-concurrency.test", password="x", is_admin=True,
        )
        self.application = make_application(
            self.session, self.grade, status=AdmissionStatus.ACCEPTED,
        )

    def _enroll(self, barrier):
        connections.close_all()
        try:
            with schema_context(self.tenant.schema_name):
                application = AdmissionApplication.objects.get(pk=self.application.pk)
                classroom = type(self.classroom).objects.get(pk=self.classroom.pk)
                actor = CustomUser.objects.get(pk=self.actor.pk)
                barrier.wait()
                try:
                    student = AdmissionEnrollmentService.enroll(
                        application=application, classroom=classroom, actor=actor,
                    )
                    return "success", student.pk
                except ValidationError as exc:
                    return "rejected", str(exc)
        finally:
            connections.close_all()

    @patch.object(AdmissionEnrollmentService, "_issue_parent_invitation")
    def test_two_simultaneous_enrollments_create_exactly_one_student(self, _invite):
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self._enroll(barrier), range(2)))

        self.application.refresh_from_db()
        self.classroom.refresh_from_db()
        self.assertEqual([result[0] for result in results].count("success"), 1)
        self.assertEqual([result[0] for result in results].count("rejected"), 1)
        self.assertEqual(Student.objects.count(), 1)
        self.assertEqual(StudentClassEnrollment.objects.filter(is_active=True).count(), 1)
        self.assertIsNotNone(self.application.enrolled_student_id)
        self.assertEqual(self.application.status, AdmissionStatus.ENROLLED)
        self.assertEqual(self.classroom.occupied_sits, 1)
