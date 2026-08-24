from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from school.testcases import TenantTestCase

from academic.models import Student
from administration.models import AcademicYear, Term
from finance.models import FeePaymentAllocation, FeeStructure, Receipt, StudentFeeAssignment
from finance.services import FeeAssignmentService, PaymentAllocationService


User = get_user_model()


class FinanceIntegrityTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        return super().setup_tenant(tenant)

    def setUp(self):
        self.user = User.objects.create_user(email="finance-integrity@test.local", password="x", is_accountant=True)
        year = AcademicYear.objects.create(
            name="2027/2028",
            start_date=date(2027, 9, 1),
            end_date=date(2028, 7, 1),
            active_year=True,
        )
        self.term = Term.objects.create(
            name="First",
            academic_year=year,
            start_date=date(2027, 9, 1),
            end_date=date(2027, 12, 1),
        )
        self.student = Student.objects.create(
            first_name="Fee",
            last_name="Owner",
            parent_contact="08090000001",
        )
        self.other_student = Student.objects.create(
            first_name="Other",
            last_name="Owner",
            parent_contact="08090000002",
        )
        self.fee = FeeStructure.objects.create(
            name="Integrity Tuition",
            amount=Decimal("1000.00"),
            academic_year=year,
            term=self.term,
            created_by=self.user,
        )
        self.fee.auto_assign_to_students(term=self.term)
        self.assignment = StudentFeeAssignment.objects.get(
            student=self.student, fee_structure=self.fee, term=self.term
        )
        self.other_assignment = StudentFeeAssignment.objects.get(
            student=self.other_student, fee_structure=self.fee, term=self.term
        )
        self.receipt = Receipt.objects.create(
            student=self.student,
            amount=Decimal("500.00"),
            term=self.term,
            received_by=self.user,
        )

    def test_allocation_updates_balance_and_deletion_reverses_it(self):
        allocation = FeePaymentAllocation.objects.create(
            receipt=self.receipt,
            fee_assignment=self.assignment,
            amount=Decimal("200.00"),
            allocated_by=self.user,
        )
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.amount_paid, Decimal("200.00"))

        allocation.delete()
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.amount_paid, Decimal("0.00"))

    def test_receipt_deletion_reverses_all_allocations(self):
        second_fee = FeeStructure.objects.create(
            name="Integrity Books",
            amount=Decimal("400.00"),
            academic_year=self.term.academic_year,
            term=self.term,
            created_by=self.user,
        )
        second_fee.auto_assign_to_students(term=self.term)
        second_assignment = StudentFeeAssignment.objects.get(
            student=self.student, fee_structure=second_fee, term=self.term
        )
        FeePaymentAllocation.objects.create(
            receipt=self.receipt,
            fee_assignment=self.assignment,
            amount=Decimal("300.00"),
            allocated_by=self.user,
        )
        FeePaymentAllocation.objects.create(
            receipt=self.receipt,
            fee_assignment=second_assignment,
            amount=Decimal("200.00"),
            allocated_by=self.user,
        )
        self.receipt.delete()
        self.assignment.refresh_from_db()
        second_assignment.refresh_from_db()
        self.assertEqual(self.assignment.amount_paid, Decimal("0.00"))
        self.assertEqual(second_assignment.amount_paid, Decimal("0.00"))

    def test_cross_student_allocation_is_rejected(self):
        with self.assertRaises(ValidationError):
            FeePaymentAllocation.objects.create(
                receipt=self.receipt,
                fee_assignment=self.other_assignment,
                amount=Decimal("100.00"),
                allocated_by=self.user,
            )

    def test_posted_allocation_is_immutable(self):
        allocation = FeePaymentAllocation.objects.create(
            receipt=self.receipt,
            fee_assignment=self.assignment,
            amount=Decimal("100.00"),
            allocated_by=self.user,
        )
        allocation.amount = Decimal("200.00")
        with self.assertRaises(ValidationError):
            allocation.save()

    def test_database_rejects_invalid_financial_amounts(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Receipt.objects.bulk_create([
                Receipt(
                    student=self.student,
                    amount=Decimal("0.00"),
                    term=self.term,
                    received_by=self.user,
                    receipt_number=999999,
                )
            ])

        with self.assertRaises(IntegrityError), transaction.atomic():
            StudentFeeAssignment.objects.filter(pk=self.assignment.pk).update(
                amount_paid=Decimal("1001.00")
            )

    def test_mandatory_assignment_is_idempotent(self):
        before = StudentFeeAssignment.objects.filter(fee_structure=self.fee).count()
        self.assertEqual(FeeAssignmentService.assign_fee(fee_structure=self.fee, term=self.term), 0)
        self.assertEqual(StudentFeeAssignment.objects.filter(fee_structure=self.fee).count(), before)

    def test_safe_bulk_allocation_preserves_receipt_and_assignment_balances(self):
        allocations = PaymentAllocationService.allocate(
            receipt=self.receipt,
            allocations=[{"fee_assignment_id": self.assignment.pk, "amount": "250.00"}],
            actor=self.user,
        )
        self.assignment.refresh_from_db()
        self.receipt.refresh_from_db()
        self.assertEqual(len(allocations), 1)
        self.assertEqual(self.assignment.amount_paid, Decimal("250.00"))
        self.assertEqual(self.receipt.unallocated_amount, Decimal("250.00"))
