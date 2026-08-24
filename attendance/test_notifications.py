from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.utils import timezone
from school.testcases import TenantTestCase

from academic.models import Parent, Student
from attendance.services import StudentAttendanceService
from attendance.models import AttendanceEvent
from notifications.models import Notification


User = get_user_model()


class AttendanceNotificationTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        return super().setup_tenant(tenant)

    def setUp(self):
        self.admin = User.objects.create_user(email="attendance-admin@test.local", password="x", is_admin=True)
        parent_user = User.objects.create_user(email="attendance-parent@test.local", password="x", is_parent=True)
        parent = Parent.objects.create(user=parent_user, phone_number="08082220001")
        self.student = Student.objects.create(
            first_name="Notify", last_name="Student", parent_contact=parent.phone_number
        )
        self.day = date(2028, 10, 2)

    def mark(self, status):
        with self.captureOnCommitCallbacks(execute=True):
            StudentAttendanceService.mark_manual(
                student=self.student, attendance_date=self.day, classroom=None,
                status_name=status, marked_by=self.admin,
            )

    def test_absent_transition_notifies_once_and_reconciliation_is_idempotent(self):
        self.mark("Absent")
        self.mark("Absent")
        self.assertEqual(Notification.objects.filter(notification_type="attendance").count(), 1)

        self.mark("Present")
        self.mark("Present")
        self.assertEqual(Notification.objects.filter(notification_type="attendance").count(), 2)
        self.assertEqual(
            Notification.objects.values("idempotency_key").distinct().count(), 2
        )

    def test_rfid_reconciliation_does_not_duplicate_transition_notification(self):
        self.mark("Absent")
        occurred_at = timezone.make_aware(datetime.combine(self.day, datetime.min.time()))
        with self.captureOnCommitCallbacks(execute=True):
            StudentAttendanceService.mark_rfid(
                student=self.student, occurred_at=occurred_at,
                direction=AttendanceEvent.EventType.ENTRY,
            )
        with self.captureOnCommitCallbacks(execute=True):
            StudentAttendanceService.mark_rfid(
                student=self.student, occurred_at=occurred_at,
                direction=AttendanceEvent.EventType.ENTRY,
            )
        self.assertEqual(Notification.objects.filter(notification_type="attendance").count(), 2)
