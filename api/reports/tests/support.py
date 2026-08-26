from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from school.testcases import TenantTestCase

from academic.models import (
    AllocatedSubject, ClassRoom, GradeLevel, Parent, Student,
    Subject, Teacher,
)
from administration.models import AcademicYear, Term
from attendance.services import StudentAttendanceService
from finance.models import FeeStructure, StudentFeeAssignment
from tenants.models import TenantStatus


User = get_user_model()


class ReportsTestCase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.name = "Reports Test School"
        tenant.status = TenantStatus.ACTIVE

    @classmethod
    def setup_domain(cls, domain):
        domain.is_primary = True
        return domain

    def setUp(self):
        self.client = APIClient(HTTP_HOST=self.domain.domain)
        self.admin = User.objects.create_user(email="admin@reports.test", password="x", is_admin=True)
        self.accountant = User.objects.create_user(email="accountant@reports.test", password="x", is_accountant=True)
        self.teacher_user = User.objects.create_user(email="teacher@reports.test", password="x", is_teacher=True)
        self.parent_user = User.objects.create_user(email="parent@reports.test", password="x", is_parent=True)
        self.student_user = User.objects.create_user(email="student@reports.test", password="x", is_student=True)
        self.staff = User.objects.create_user(email="staff@reports.test", password="x", is_staff=True)
        self.teacher = Teacher.objects.create(user=self.teacher_user, empId="RPT-T1", short_name="RT1")
        self.parent = Parent.objects.create(user=self.parent_user, phone_number="08095550001")
        today = timezone.localdate()
        self.year = AcademicYear.objects.create(
            name=f"{today.year} Reports", start_date=date(today.year, 1, 1),
            end_date=date(today.year, 12, 31), active_year=True,
        )
        self.term = Term.objects.create(
            name="Reports Term", academic_year=self.year,
            start_date=date(today.year, 1, 1), end_date=date(today.year, 12, 31),
        )
        self.grade = GradeLevel.objects.create(
            system_code="JSS_1", section="JSS", default_name="JSS 1", sequence_order=1,
        )
        self.own_class = ClassRoom.objects.create(name="Reports A", grade_level=self.grade, class_teacher=self.teacher)
        self.other_class = ClassRoom.objects.create(name="Reports B", grade_level=self.grade)
        subject = Subject.objects.create(name="Report Mathematics", subject_code="RPT-MTH")
        AllocatedSubject.objects.create(
            teacher_name=self.teacher, subject=subject, academic_year=self.year,
            term=self.term, class_room=self.own_class, weekly_periods=3,
        )
        self.own_student = Student.objects.create(
            user=self.student_user, first_name="Assigned", last_name="Student",
            parent_contact=self.parent.phone_number, classroom=self.own_class,
        )
        self.other_student = Student.objects.create(
            first_name="Unrelated", last_name="Student",
            parent_contact="08095550002", classroom=self.other_class,
        )
        for student, classroom in (
            (self.own_student, self.own_class), (self.other_student, self.other_class),
        ):
            StudentAttendanceService.mark_manual(
                student=student, attendance_date=today, classroom=classroom,
                status_name="Present", marked_by=self.admin, term=self.term,
            )
        fee = FeeStructure.objects.create(
            name="Report Tuition", amount=Decimal("1000"), academic_year=self.year,
            term=self.term, created_by=self.admin,
        )
        fee.auto_assign_to_students(term=self.term)
        for student in (self.own_student, self.other_student):
            StudentFeeAssignment.objects.get_or_create(
                student=student, fee_structure=fee, term=self.term,
                defaults={"amount_owed": Decimal("1000")},
            )

    def get_as(self, user, url, data=None):
        self.client.force_authenticate(user)
        return self.client.get(url, data or {})

    def post_as(self, user, url, data=None):
        self.client.force_authenticate(user)
        return self.client.post(url, data or {}, format="json")
