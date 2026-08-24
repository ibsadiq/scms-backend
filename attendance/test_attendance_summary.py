from datetime import date
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from school.testcases import TenantTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from academic.models import ClassLevel, ClassRoom, GradeLevel, Student
from administration.models import AcademicYear, Term
from attendance.models import AttendanceStatus, StudentAttendance, StudentTermAttendanceSummary
from attendance.services import AttendanceSummaryService
from examination.services.report_card_generator import ReportCardGenerator
from attendance.views_summary import StudentTermAttendanceSummaryViewSet


User = get_user_model()


class StudentTermAttendanceSummaryTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        return super().setup_tenant(tenant)

    def setUp(self):
        self.admin = User.objects.create_user(
            email="summary-admin@example.com", password="test", is_admin=True, is_staff=True
        )
        self.teacher_user = User.objects.create_user(
            email="summary-teacher@example.com", password="test", is_teacher=True
        )
        year = AcademicYear.objects.create(
            name="2026/2027", start_date=date(2026, 9, 1), end_date=date(2027, 7, 31), active_year=True
        )
        self.term = Term.objects.create(
            name="First Term", academic_year=year,
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15),
        )
        grade = GradeLevel.objects.create(
            system_code="JSS_1", section="JSS", default_name="JSS 1", sequence_order=1
        )
        level = ClassLevel.objects.create(name="JSS 1 A", grade_level=grade)
        self.classroom = ClassRoom.objects.create(name=level)
        self.student = Student.objects.create(
            first_name="Amina", last_name="Bello", parent_contact="08020000001", classroom=self.classroom
        )
        self.present = AttendanceStatus.objects.create(name="Present", code="P")
        self.absent = AttendanceStatus.objects.create(name="Absent", code="A", absent=True)
        self.late = AttendanceStatus.objects.create(name="Late", code="L", late=True)
        self.factory = APIRequestFactory()

    def call_summary_view(self, method, path, user=None, data=None, pk=None):
        request = getattr(self.factory, method)(path, data or {}, format="json")
        if user:
            force_authenticate(request, user=user)
        action = "create" if method == "post" else "partial_update"
        view = StudentTermAttendanceSummaryViewSet.as_view({method: action})
        return view(request, **({"pk": pk} if pk is not None else {}))

    def summary(self, **overrides):
        values = {
            "student": self.student, "term": self.term, "school_days": 64,
            "days_present": 58, "days_absent": 6, "times_late": 3,
            "source": StudentTermAttendanceSummary.Source.MANUAL, "entered_by": self.admin,
        }
        values.update(overrides)
        return StudentTermAttendanceSummary(**values)

    def test_validation_rejects_invalid_counts(self):
        for overrides in [
            {"days_present": 65}, {"days_absent": 65},
            {"days_present": 60, "days_absent": 5}, {"times_late": -1},
        ]:
            with self.subTest(overrides=overrides), self.assertRaises(ValidationError):
                self.summary(**overrides).full_clean()

    def test_database_enforces_unique_student_term(self):
        self.summary().save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.summary(source=StudentTermAttendanceSummary.Source.IMPORTED).save()

    def test_manual_api_create_and_update_sets_actor_without_daily_rows(self):
        payload = {
            "student": self.student.pk, "term": self.term.pk, "school_days": 64,
            "days_present": 58, "days_absent": 6, "times_late": 3, "notes": "Paper register",
        }
        response = self.call_summary_view("post", "/api/attendance/term-summaries/", self.admin, payload)
        self.assertEqual(response.status_code, 201, response.data)
        summary = StudentTermAttendanceSummary.objects.get()
        self.assertEqual(summary.entered_by, self.admin)
        self.assertEqual(summary.source, StudentTermAttendanceSummary.Source.MANUAL)
        self.assertEqual(StudentAttendance.objects.count(), 0)

        response = self.call_summary_view(
            "patch", f"/api/attendance/term-summaries/{summary.pk}/", self.admin,
            {"days_present": 57, "days_absent": 7}, pk=summary.pk,
        )
        self.assertEqual(response.status_code, 200, response.data)
        summary.refresh_from_db()
        self.assertEqual((summary.days_present, summary.days_absent), (57, 7))
        self.assertEqual(StudentAttendance.objects.count(), 0)

    def test_summary_api_permissions(self):
        payload = {
            "student": self.student.pk, "term": self.term.pk, "school_days": 1,
            "days_present": 1, "days_absent": 0,
        }
        self.assertEqual(self.call_summary_view("post", "/api/attendance/term-summaries/", data=payload).status_code, 401)
        self.assertEqual(
            self.call_summary_view("post", "/api/attendance/term-summaries/", self.teacher_user, payload).status_code,
            403,
        )

    def test_ssync_calculation_uses_status_flags_and_operational_dates(self):
        for attendance_date, status in [
            (date(2026, 9, 2), self.present),
            (date(2026, 9, 3), self.late),
            (date(2026, 9, 4), self.absent),
        ]:
            StudentAttendance.objects.create(
                student=self.student, date=attendance_date, ClassRoom=self.classroom,
                term=self.term, status=status, marked_by=self.admin,
            )
        summary = AttendanceSummaryService.calculate_from_ssync(student=self.student, term=self.term)
        self.assertEqual(summary.source, StudentTermAttendanceSummary.Source.SSYNC)
        self.assertEqual((summary.school_days, summary.days_present, summary.days_absent, summary.times_late), (3, 2, 1, 1))

    def test_manual_and_imported_summaries_take_precedence(self):
        manual = AttendanceSummaryService.save_manual_summary(
            student=self.student, term=self.term, entered_by=self.admin,
            school_days=64, days_present=58, days_absent=6, times_late=3,
        )
        self.assertEqual(AttendanceSummaryService.get_for_report_card(student=self.student, term=self.term).pk, manual.pk)

        imported = AttendanceSummaryService.save_imported_summary(
            student=self.student, term=self.term, entered_by=self.admin,
            school_days=65, days_present=59, days_absent=6, times_late=2,
        )
        resolved = AttendanceSummaryService.get_for_report_card(student=self.student, term=self.term)
        self.assertEqual(resolved.pk, imported.pk)
        self.assertEqual(resolved.source, StudentTermAttendanceSummary.Source.IMPORTED)

    def test_report_card_generator_uses_resolved_manual_and_ssync_summaries(self):
        AttendanceSummaryService.save_manual_summary(
            student=self.student, term=self.term, entered_by=self.admin,
            school_days=64, days_present=58, days_absent=6, times_late=3,
        )
        generator = ReportCardGenerator(SimpleNamespace(student=self.student, term=self.term))
        self.assertEqual(generator._get_attendance_stats()["source"], "MANUAL")
        self.assertEqual(generator._get_attendance_stats()["present"], 58)

        StudentTermAttendanceSummary.objects.all().delete()
        StudentAttendance.objects.create(
            student=self.student, date=date(2026, 9, 2), ClassRoom=self.classroom,
            term=self.term, status=self.present, marked_by=self.admin,
        )
        stats = generator._get_attendance_stats()
        self.assertEqual(stats["source"], "SSYNC")
        self.assertEqual((stats["present"], stats["total_days"]), (1, 1))
