from datetime import date

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from school.testcases import TenantTestCase

from academic.models import (
    AllocatedSubject,
    ClassRoom,
    GradeLevel,
    Parent,
    Student,
    Subject,
    Teacher,
)
from administration.models import AcademicYear, Term
from tenants.models import TenantStatus


User = get_user_model()


class SISAccessTestCase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.name = "SIS Scope School"
        tenant.status = TenantStatus.ACTIVE

    def setUp(self):
        self.client = APIClient(HTTP_HOST=self.domain.domain)
        self.admin = User.objects.create_user(email="admin@sis.test", password="x", is_admin=True)
        self.teacher_user = User.objects.create_user(
            email="teacher@sis.test", password="x", is_teacher=True
        )
        self.teacher = Teacher.objects.create(user=self.teacher_user, empId="SIS-T1", short_name="S1")
        self.parent_user = User.objects.create_user(
            email="parent@sis.test", password="x", is_parent=True
        )
        self.parent = Parent.objects.create(user=self.parent_user, phone_number="08110000001")
        self.student_user = User.objects.create_user(
            email="student@sis.test", password="x", is_student=True
        )
        self.accountant = User.objects.create_user(
            email="accountant@sis.test", password="x", is_accountant=True
        )
        self.staff = User.objects.create_user(email="staff@sis.test", password="x", is_staff=True)

        year = AcademicYear.objects.create(
            name="2028/2029", start_date=date(2028, 9, 1), end_date=date(2029, 7, 1), active_year=True
        )
        term = Term.objects.create(
            name="First", academic_year=year,
            start_date=date(2028, 9, 1), end_date=date(2028, 12, 1),
        )
        grade = GradeLevel.objects.create(
            system_code="JSS_1", section="JSS", default_name="JSS 1", sequence_order=1
        )
        self.assigned_class = ClassRoom.objects.create(name="Assigned", grade_level=grade, class_teacher=self.teacher)
        self.other_class = ClassRoom.objects.create(name="Other", grade_level=grade)
        subject = Subject.objects.create(name="SIS Mathematics", subject_code="SISM")
        AllocatedSubject.objects.create(
            teacher_name=self.teacher, subject=subject, academic_year=year, term=term,
            class_room=self.assigned_class, weekly_periods=3,
        )

        self.own_student = Student.objects.create(
            user=self.student_user, first_name="Own", last_name="Learner",
            parent_contact=self.parent.phone_number, classroom=self.assigned_class,
            can_login=True,
        )
        self.other_student = Student.objects.create(
            first_name="Other", last_name="Learner", parent_contact="08110000002",
            classroom=self.other_class,
        )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    @staticmethod
    def rows(response):
        return response.data.get("results", response.data)

    def list_ids(self, user, params=None):
        self.authenticate(user)
        response = self.client.get("/api/sis/students/", params or {})
        return response, {row["id"] for row in self.rows(response)} if response.status_code == 200 else set()
