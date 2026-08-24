from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import connections
from django_tenants.utils import schema_context

from academic.models import Student
from administration.models import AcademicYear, Term
from finance.models import FeeStructure, StudentFeeAssignment
from finance.services import FeeAssignmentService
from school.testcases import TenantTransactionTestCase


User = get_user_model()


class FeeAssignmentConcurrencyTests(TenantTransactionTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.name = "Finance Race Academy"

    def setUp(self):
        user = User.objects.create_user(email="finance-race@test.local", password="x")
        year = AcademicYear.objects.create(
            name="2030/2031", start_date=date(2030, 9, 1),
            end_date=date(2031, 7, 1), active_year=True,
        )
        self.term = Term.objects.create(
            name="First", academic_year=year, start_date=date(2030, 9, 1),
            end_date=date(2030, 12, 1),
        )
        self.student = Student.objects.create(
            first_name="Finance", last_name="Race", parent_contact="08083330001",
        )
        self.fee = FeeStructure.objects.create(
            name="Race Tuition", amount=Decimal("1000"), academic_year=year,
            term=self.term, created_by=user,
        )
        StudentFeeAssignment.objects.filter(
            student=self.student, fee_structure=self.fee, term=self.term
        ).delete()

    def test_concurrent_mandatory_assignment_is_idempotent(self):
        barrier = Barrier(2)

        def assign(_):
            connections.close_all()
            try:
                with schema_context(self.tenant.schema_name):
                    barrier.wait()
                    return FeeAssignmentService.assign_fee_to_student(
                        fee_structure=FeeStructure.objects.get(pk=self.fee.pk),
                        student=Student.objects.get(pk=self.student.pk),
                        term=Term.objects.get(pk=self.term.pk),
                    )
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(assign, range(2)))
        self.assertEqual(sorted(outcomes), [0, 1])
        self.assertEqual(StudentFeeAssignment.objects.filter(
            student=self.student, fee_structure=self.fee, term=self.term
        ).count(), 1)

