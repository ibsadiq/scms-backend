from django.test import SimpleTestCase

from attendance.permissions import AttendanceRecordPermission, CanReadAssignedAttendance
from attendance.views import PeriodAttendanceDetailView, PeriodAttendanceListView, TeacherAttendanceDetailView, TeacherAttendanceListView


class AttendancePermissionUnitTests(SimpleTestCase):
    def test_legacy_views_are_explicitly_protected_and_read_only(self):
        for view in (TeacherAttendanceListView, TeacherAttendanceDetailView, PeriodAttendanceListView, PeriodAttendanceDetailView):
            self.assertEqual(view.permission_classes, [CanReadAssignedAttendance])
        self.assertFalse(hasattr(TeacherAttendanceListView, 'post'))
        self.assertFalse(hasattr(TeacherAttendanceDetailView, 'put'))
        self.assertFalse(hasattr(PeriodAttendanceListView, 'post'))
        self.assertFalse(hasattr(PeriodAttendanceDetailView, 'delete'))

    def test_modern_attendance_uses_domain_permission(self):
        from attendance.views_student import StudentAttendanceViewSet
        self.assertEqual(StudentAttendanceViewSet.permission_classes, [AttendanceRecordPermission])
