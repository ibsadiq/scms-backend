from django.core.cache import cache
from rest_framework.test import APIClient
from school.testcases import TenantTestCase

from academic.models import (
    AllocatedSubject, ClassLevel, ClassRoom, GradeLevel, Parent, Student,
    Subject, Teacher,
)
from administration.models import AcademicYear, Term
from tenants.models import TenantStatus
from users.models import CustomUser


class MessagingTestCase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.name = "Messaging Test School"
        tenant.status = TenantStatus.ACTIVE

    @classmethod
    def setup_domain(cls, domain):
        domain.is_primary = True
        return domain

    def setUp(self):
        cache.clear()
        self.client = APIClient(HTTP_HOST=self.domain.domain)
        self.admin = CustomUser.objects.create_user(
            email="admin@messages.test", password="x", is_admin=True,
            first_name="School", last_name="Admin",
        )
        self.teacher_user = CustomUser.objects.create_user(
            email="teacher@messages.test", password="x", is_teacher=True,
            first_name="Assigned", last_name="Teacher",
        )
        self.other_teacher_user = CustomUser.objects.create_user(
            email="other-teacher@messages.test", password="x", is_teacher=True,
        )
        self.parent_user = CustomUser.objects.create_user(
            email="parent@messages.test", password="x", is_parent=True,
            first_name="Linked", last_name="Parent",
        )
        self.other_parent_user = CustomUser.objects.create_user(
            email="other-parent@messages.test", password="x", is_parent=True,
        )
        self.student_user = CustomUser.objects.create_user(
            email="student@messages.test", password="x", is_student=True,
        )
        self.other_student_user = CustomUser.objects.create_user(
            email="other-student@messages.test", password="x", is_student=True,
        )
        self.accountant = CustomUser.objects.create_user(
            email="accountant@messages.test", password="x", is_accountant=True,
        )
        self.staff = CustomUser.objects.create_user(
            email="staff@messages.test", password="x", is_staff=True,
        )
        self.teacher = Teacher.objects.create(
            user=self.teacher_user, empId="MSG-T1", short_name="MT1",
        )
        self.other_teacher = Teacher.objects.create(
            user=self.other_teacher_user, empId="MSG-T2", short_name="MT2",
        )
        self.parent = Parent.objects.create(
            user=self.parent_user, phone_number="08096660001",
        )
        self.other_parent = Parent.objects.create(
            user=self.other_parent_user, phone_number="08096660002",
        )
        from datetime import date
        self.year = AcademicYear.objects.create(
            name="2034 Messaging", start_date=date(2034, 1, 1),
            end_date=date(2034, 12, 31), active_year=True,
        )
        self.term = Term.objects.create(
            name="Messaging Term", academic_year=self.year,
            start_date=date(2034, 1, 1), end_date=date(2034, 12, 31),
        )
        grade = GradeLevel.objects.create(
            system_code="JSS_1", section="JSS", default_name="JSS 1", sequence_order=1,
        )
        own_level = ClassLevel.objects.create(name="Messaging A", grade_level=grade)
        other_level = ClassLevel.objects.create(name="Messaging B", grade_level=grade)
        self.own_class = ClassRoom.objects.create(name=own_level, class_teacher=self.teacher)
        self.other_class = ClassRoom.objects.create(name=other_level, class_teacher=self.other_teacher)
        subject = Subject.objects.create(name="Messaging Subject", subject_code="MSG")
        AllocatedSubject.objects.create(
            teacher_name=self.teacher, subject=subject, academic_year=self.year,
            term=self.term, class_room=self.own_class, weekly_periods=1,
        )
        self.student = Student.objects.create(
            user=self.student_user, first_name="Linked", last_name="Student",
            parent_contact=self.parent.phone_number, parent_guardian=self.parent,
            classroom=self.own_class,
        )
        self.other_student = Student.objects.create(
            user=self.other_student_user, first_name="Other", last_name="Student",
            parent_contact=self.other_parent.phone_number,
            parent_guardian=self.other_parent, classroom=self.other_class,
        )

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def post_message(self, sender, recipient, *, student=None, parent_message=None):
        self.client.force_authenticate(sender)
        payload = {"recipient": recipient.pk, "subject": "Hello", "body": "Message body"}
        if student is not None:
            payload["student"] = student.pk
        if parent_message is not None:
            payload["parent_message"] = parent_message.pk
        return self.client.post("/api/notifications/messages/", payload, format="json")
