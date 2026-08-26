from datetime import date

from django.contrib.auth import get_user_model
from school.testcases import TenantTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from academic.models import AllocatedSubject, ClassRoom, GradeLevel, Parent, Student, Subject, Teacher
from administration.models import AcademicYear, Term
from attendance.models import AttendanceEvent, StudentAttendance, TeachersAttendance
from attendance.services import StudentAttendanceService
from attendance.views import TeacherAttendanceListView
from attendance.views_student import StudentAttendanceViewSet


User = get_user_model()


class AttendanceAuthorizationTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.status = "active"
        return super().setup_tenant(tenant)

    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = User.objects.create_user(email="admin@school.test", password="x", is_admin=True)
        self.teacher_user = User.objects.create_user(email="teacher@school.test", password="x", is_teacher=True)
        self.teacher = Teacher.objects.create(user=self.teacher_user, empId="T-1", short_name="T1")
        self.student_user = User.objects.create_user(email="student@school.test", password="x", is_student=True)
        self.parent_user = User.objects.create_user(email="parent@school.test", password="x", is_parent=True)
        self.parent = Parent.objects.create(user=self.parent_user, phone_number="08000000010")
        year = AcademicYear.objects.create(name="2026/2027", start_date=date(2026, 9, 1), end_date=date(2027, 7, 1), active_year=True)
        self.term = Term.objects.create(name="First", academic_year=year, start_date=date(2026, 9, 1), end_date=date(2026, 12, 1))
        grade = GradeLevel.objects.create(system_code="JSS_1", section="JSS", default_name="JSS 1", sequence_order=1)
        self.assigned_class = ClassRoom.objects.create(name="A", grade_level=grade, class_teacher=self.teacher)
        self.other_class = ClassRoom.objects.create(name="B", grade_level=grade)
        subject = Subject.objects.create(name="Mathematics", subject_code="MTH")
        AllocatedSubject.objects.create(teacher_name=self.teacher, subject=subject, academic_year=year, term=self.term, class_room=self.assigned_class, weekly_periods=3)
        self.own_student = Student.objects.create(user=self.student_user, first_name="Own", last_name="Student", parent_contact=self.parent.phone_number, classroom=self.assigned_class)
        self.other_student = Student.objects.create(first_name="Other", last_name="Student", parent_contact="08000000012", classroom=self.other_class)
        for student, classroom in ((self.own_student, self.assigned_class), (self.other_student, self.other_class)):
            StudentAttendanceService.mark_manual(student=student, attendance_date=date(2026, 9, 2), classroom=classroom, status_name="Present", marked_by=self.admin, term=self.term)

    def _list_ids(self, user):
        request = self.factory.get("/api/attendance/student-attendance/")
        force_authenticate(request, user=user)
        response = StudentAttendanceViewSet.as_view({'get': 'list'})(request)
        rows = response.data.get('results', response.data)
        return response.status_code, {row['student_id'] for row in rows}

    def test_student_parent_and_teacher_reads_are_scoped(self):
        self.assertEqual(self._list_ids(self.student_user)[1], {self.own_student.id})
        self.assertEqual(self._list_ids(self.parent_user)[1], {self.own_student.id})
        self.assertEqual(self._list_ids(self.teacher_user)[1], {self.own_student.id})

    def test_anonymous_is_rejected_and_admin_sees_school(self):
        response = StudentAttendanceViewSet.as_view({'get': 'list'})(self.factory.get('/'))
        self.assertIn(response.status_code, (401, 403))
        self.assertEqual(self._list_ids(self.admin)[1], {self.own_student.id, self.other_student.id})

    def test_teacher_cannot_mutate_unrelated_class(self):
        request = self.factory.post('/', {'student': self.other_student.id, 'classroom': self.other_class.id, 'date': '2026-09-03', 'status': 'Present'}, format='json')
        force_authenticate(request, user=self.teacher_user)
        response = StudentAttendanceViewSet.as_view({'post': 'create'})(request)
        self.assertEqual(response.status_code, 403)

    def test_service_backed_correction_creates_event(self):
        record = StudentAttendance.objects.get(student=self.own_student)
        before = AttendanceEvent.objects.count()
        request = self.factory.patch('/', {'status': 'Late'}, format='json')
        force_authenticate(request, user=self.teacher_user)
        response = StudentAttendanceViewSet.as_view({'patch': 'partial_update'})(request, pk=record.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AttendanceEvent.objects.count(), before + 1)

    def test_legacy_teacher_attendance_write_is_frozen(self):
        request = self.factory.post('/', {}, format='json')
        force_authenticate(request, user=self.admin)
        response = TeacherAttendanceListView.as_view()(request)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(TeachersAttendance.objects.count(), 0)
