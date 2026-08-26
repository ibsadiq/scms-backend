from datetime import date, time

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from school.testcases import TenantTestCase

from academic.models import ClassRoom, GradeLevel, Staff, Student
from administration.models import AcademicYear, Term
from attendance.models import AttendanceEvent, AttendancePolicy, StaffAttendance, StudentAttendance
from attendance.services import AttendanceEventService, StaffAttendanceService, StudentAttendanceService


User = get_user_model()


class AttendanceServiceFoundationTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        return super().setup_tenant(tenant)

    def setUp(self):
        self.user = User.objects.create_user(email="marker@example.com", password="test", is_admin=True)
        year = AcademicYear.objects.create(
            name="2026/2027", start_date=date(2026, 9, 1), end_date=date(2027, 7, 31), active_year=True
        )
        self.term = Term.objects.create(
            name="First Term", academic_year=year, start_date=date(2026, 9, 1), end_date=date(2026, 12, 15)
        )
        grade = GradeLevel.objects.create(
            system_code="JSS_1", section="JSS", default_name="JSS 1", sequence_order=1
        )
        self.classroom = ClassRoom.objects.create(name="A", grade_level=grade)
        self.student = Student.objects.create(
            first_name="Ibrahim", last_name="Musa", parent_contact="08010000001", classroom=self.classroom
        )
        self.staff = Staff.objects.create(user=self.user, role=Staff.Role.ADMINISTRATOR)

    def test_manual_student_flow_preserves_one_row_and_records_correction(self):
        first, created = StudentAttendanceService.mark_manual(
            student=self.student, attendance_date=date(2026, 9, 2), classroom=self.classroom,
            status_name="Present", marked_by=self.user, term=self.term,
        )
        second, created_again = StudentAttendanceService.mark_manual(
            student=self.student, attendance_date=date(2026, 9, 2), classroom=self.classroom,
            status_name="Late", marked_by=self.user, term=self.term, time_in=time(8, 15),
        )
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(StudentAttendance.objects.count(), 1)
        self.assertEqual(AttendanceEvent.objects.count(), 2)

    def test_staff_attendance_is_one_row_per_staff_date(self):
        first, _ = StaffAttendanceService.mark_manual(
            staff=self.staff, attendance_date=date(2026, 9, 2), status_name="Present", marked_by=self.user,
            time_in=time(7, 0),
        )
        second, created = StaffAttendanceService.mark_manual(
            staff=self.staff, attendance_date=date(2026, 9, 2), status_name="Present", marked_by=self.user,
            time_in=time(7, 5), time_out=time(16, 0),
        )
        self.assertFalse(created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(StaffAttendance.objects.count(), 1)

    def test_configured_staff_late_threshold_is_applied_by_service(self):
        AttendancePolicy.objects.create(staff_late_after=time(7, 0))
        attendance, _ = StaffAttendanceService.mark_manual(
            staff=self.staff, attendance_date=date(2026, 9, 3), status_name="Present",
            marked_by=self.user, time_in=time(7, 1),
        )
        self.assertTrue(attendance.status.late)

    def test_event_service_requires_exactly_one_subject(self):
        with self.assertRaises(ValueError):
            AttendanceEventService.record(
                source=AttendanceEvent.Source.MANUAL,
                event_type=AttendanceEvent.EventType.MARKED_PRESENT,
                performed_by=self.user,
            )
        with self.assertRaises(ValueError):
            AttendanceEventService.record(
                student=self.student, staff=self.staff,
                source=AttendanceEvent.Source.MANUAL,
                event_type=AttendanceEvent.EventType.MARKED_PRESENT,
            )

    def test_event_is_immutable(self):
        event = AttendanceEventService.record(
            staff=self.staff, source=AttendanceEvent.Source.MANUAL,
            event_type=AttendanceEvent.EventType.MARKED_PRESENT, performed_by=self.user,
        )
        event.metadata = {"changed": True}
        with self.assertRaises(ValueError):
            event.save()
