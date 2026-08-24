from datetime import date

from django.contrib.auth import get_user_model
from django.db import transaction
from school.testcases import TenantTestCase

from academic.models import Student, Subject, Teacher
from administration.models import AcademicYear, Term
from examination.models import AssessmentSession, AssessmentType, MarkedScript
from notifications.models import Notification


User = get_user_model()


class MarkedScriptNotificationTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        return super().setup_tenant(tenant)

    def setUp(self):
        student_user = User.objects.create_user(
            email="script-student@test.local", password="x", is_student=True
        )
        teacher_user = User.objects.create_user(
            email="script-teacher@test.local", password="x", is_teacher=True
        )
        self.teacher = Teacher.objects.create(user=teacher_user, empId="NS01", short_name="NS")
        self.student = Student.objects.create(
            user=student_user, first_name="Script", last_name="Student",
            parent_contact="08083330001", can_login=True,
        )
        self.subject = Subject.objects.create(name="Notification Subject", subject_code="NST")
        year = AcademicYear.objects.create(
            name="2029/2030", start_date=date(2029, 9, 1),
            end_date=date(2030, 7, 1), active_year=True,
        )
        term = Term.objects.create(
            name="First", academic_year=year,
            start_date=date(2029, 9, 1), end_date=date(2029, 12, 1),
        )
        self.exam = AssessmentSession.objects.create(
            assessment_type=AssessmentType.EXAMINATION,
            name="Notification Exam", term=term, academic_year=year,
            start_date=date(2029, 10, 1), ends_date=date(2029, 10, 2),
            out_of=100, created_by=self.teacher,
        )
        with self.captureOnCommitCallbacks(execute=True):
            self.script = MarkedScript.objects.create(
                exam=self.exam, student=self.student, subject=self.subject,
                uploaded_by=self.teacher,
            )

    def test_false_to_true_notifies_once_after_commit(self):
        self.script.visible_to_student = True
        with self.captureOnCommitCallbacks(execute=True):
            self.script.save(update_fields=("visible_to_student",))
        self.assertEqual(Notification.objects.filter(notification_type="exam").count(), 1)

        with self.captureOnCommitCallbacks(execute=True):
            self.script.save(update_fields=("visible_to_student",))
        self.assertEqual(Notification.objects.filter(notification_type="exam").count(), 1)

    def test_rollback_does_not_notify(self):
        try:
            with self.captureOnCommitCallbacks(execute=True):
                with transaction.atomic():
                    self.script.visible_to_student = True
                    self.script.save(update_fields=("visible_to_student",))
                    raise RuntimeError("rollback")
        except RuntimeError:
            pass
        self.assertFalse(Notification.objects.filter(notification_type="exam").exists())
