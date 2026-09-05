from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from school.testcases import TenantTestCase

from academic.models import ClassRoom, GradeLevel, Student, StudentClassEnrollment
from academic.services.enrollment_service import EnrollmentService
from administration.models import AcademicYear, Term
from finance.models import (
    FeePaymentAllocation,
    FeeStructure,
    FeeTermSchedule,
    Receipt,
    StudentFeeAssignment,
)
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
            admission_number="INT-STD-1",
            parent_contact="08090000001",
        )
        self.other_student = Student.objects.create(
            first_name="Other",
            last_name="Owner",
            admission_number="INT-STD-2",
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


class EnrollmentFeeAssignmentTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        return super().setup_tenant(tenant)

    def setUp(self):
        self.user = User.objects.create_user(
            email="finance-enrollment@test.local", password="x", is_accountant=True
        )
        today = timezone.localdate()
        self.academic_year = AcademicYear.objects.create(
            name="2029/2030",
            start_date=today + timedelta(days=10),
            end_date=today + timedelta(days=300),
            active_year=True,
        )
        # First term starts in the future (10 days from today)
        self.term_1 = Term.objects.create(
            name="First Term",
            academic_year=self.academic_year,
            start_date=today + timedelta(days=10),
            end_date=today + timedelta(days=100),
        )
        self.term_2 = Term.objects.create(
            name="Second Term",
            academic_year=self.academic_year,
            start_date=today + timedelta(days=110),
            end_date=today + timedelta(days=200),
        )
        self.grade_jss1 = GradeLevel.objects.create(
            system_code="JSS_1", section="JSS", default_name="JSS 1", sequence_order=1
        )
        self.grade_jss2 = GradeLevel.objects.create(
            system_code="JSS_2", section="JSS", default_name="JSS 2", sequence_order=2
        )
        self.classroom_jss1a = ClassRoom.objects.create(
            name="JSS 1A", grade_level=self.grade_jss1, capacity=40
        )
        self.classroom_jss1b = ClassRoom.objects.create(
            name="JSS 1B", grade_level=self.grade_jss1, capacity=40
        )
        self.classroom_jss2a = ClassRoom.objects.create(
            name="JSS 2A", grade_level=self.grade_jss2, capacity=40
        )

        # Mandatory fee for First Term
        self.fee_first_term = FeeStructure.objects.create(
            name="First Term Tuition",
            amount=Decimal("15000.00"),
            academic_year=self.academic_year,
            term=self.term_1,
            is_mandatory=True,
            created_by=self.user,
        )
        # Mandatory fee with no term (applies to all terms)
        self.fee_all_terms = FeeStructure.objects.create(
            name="Development Levy",
            amount=Decimal("5000.00"),
            academic_year=self.academic_year,
            term=None,
            is_mandatory=True,
            created_by=self.user,
        )
        FeeTermSchedule.objects.create(
            fee_structure=self.fee_all_terms,
            term=self.term_1,
            amount=Decimal("5000.00"),
            due_date=self.term_1.start_date + timedelta(days=14),
        )
        FeeTermSchedule.objects.create(
            fee_structure=self.fee_all_terms,
            term=self.term_2,
            amount=Decimal("5000.00"),
            due_date=self.term_2.start_date + timedelta(days=14),
        )
        # Fee scoped to JSS 1 only
        self.fee_jss1_only = FeeStructure.objects.create(
            name="JSS 1 Uniform",
            amount=Decimal("3000.00"),
            academic_year=self.academic_year,
            term=self.term_1,
            is_mandatory=True,
            created_by=self.user,
        )
        self.fee_jss1_only.grade_levels.add(self.grade_jss1)

        # Fee for Second Term only
        self.fee_second_term = FeeStructure.objects.create(
            name="Second Term Tuition",
            amount=Decimal("15000.00"),
            academic_year=self.academic_year,
            term=self.term_2,
            is_mandatory=True,
            created_by=self.user,
        )

    def test_new_enrollment_auto_assigns_mandatory_fees_before_term_start(self):
        student = Student.objects.create(
            first_name="PreTerm", last_name="Enrollee", parent_contact="08011223344",
            admission_number="ENR-FEE-1",
        )
        with self.captureOnCommitCallbacks(execute=True):
            enrollment, _ = EnrollmentService.enroll(
                student=student,
                classroom=self.classroom_jss1a,
                academic_year=self.academic_year,
            )

        assignments = StudentFeeAssignment.objects.filter(student=student)
        assigned_fee_ids = set(assignments.values_list("fee_structure_id", flat=True))

        # Must assign First Term Tuition, Development Levy, and JSS 1 Uniform
        self.assertIn(self.fee_first_term.id, assigned_fee_ids)
        self.assertIn(self.fee_all_terms.id, assigned_fee_ids)
        self.assertIn(self.fee_jss1_only.id, assigned_fee_ids)

        # Must NOT assign Second Term fee yet
        self.assertNotIn(self.fee_second_term.id, assigned_fee_ids)

        # Verify amounts
        first_term_assign = assignments.get(fee_structure=self.fee_first_term)
        self.assertEqual(first_term_assign.term, self.term_1)
        self.assertEqual(first_term_assign.amount_owed, Decimal("15000.00"))

    def test_fee_assignment_is_idempotent_on_re_enrollment(self):
        student = Student.objects.create(
            first_name="Idem", last_name="Potent", parent_contact="08011223355",
            admission_number="ENR-FEE-2",
        )
        with self.captureOnCommitCallbacks(execute=True):
            enrollment, _ = EnrollmentService.enroll(
                student=student,
                classroom=self.classroom_jss1a,
                academic_year=self.academic_year,
            )
        initial_count = StudentFeeAssignment.objects.filter(student=student).count()

        # Re-enroll the same student in the same classroom
        with self.captureOnCommitCallbacks(execute=True):
            EnrollmentService.enroll(
                student=student,
                classroom=self.classroom_jss1a,
                academic_year=self.academic_year,
            )
        re_enroll_count = StudentFeeAssignment.objects.filter(student=student).count()
        self.assertEqual(initial_count, re_enroll_count)

        # Direct synchronization call should also return 0 new assignments
        new_assigned = FeeAssignmentService.sync_fees_for_enrollment(enrollment=enrollment)
        self.assertEqual(new_assigned, 0)
        self.assertEqual(StudentFeeAssignment.objects.filter(student=student).count(), initial_count)

    def test_fees_from_different_academic_year_are_never_assigned(self):
        prior_year = AcademicYear.objects.create(
            name="2028/2029",
            start_date=date(2028, 9, 1),
            end_date=date(2029, 7, 1),
            active_year=False,
        )
        prior_term = Term.objects.create(
            name="First Term",
            academic_year=prior_year,
            start_date=date(2028, 9, 1),
            end_date=date(2028, 12, 1),
        )
        prior_fee = FeeStructure.objects.create(
            name="Prior Year Fee",
            amount=Decimal("9999.00"),
            academic_year=prior_year,
            term=prior_term,
            is_mandatory=True,
            created_by=self.user,
        )
        student = Student.objects.create(
            first_name="Year", last_name="Boundary", parent_contact="08011223366",
            admission_number="ENR-FEE-3",
        )
        with self.captureOnCommitCallbacks(execute=True):
            enrollment, _ = EnrollmentService.enroll(
                student=student,
                classroom=self.classroom_jss1a,
                academic_year=self.academic_year,
            )

        self.assertFalse(
            StudentFeeAssignment.objects.filter(student=student, fee_structure=prior_fee).exists()
        )

    def test_fee_scoping_to_different_grade_level_is_excluded(self):
        student_jss2 = Student.objects.create(
            first_name="Jss2", last_name="Student", parent_contact="08011223377",
            admission_number="ENR-FEE-4",
        )
        with self.captureOnCommitCallbacks(execute=True):
            enrollment, _ = EnrollmentService.enroll(
                student=student_jss2,
                classroom=self.classroom_jss2a,
                academic_year=self.academic_year,
            )

        assigned_fee_ids = set(
            StudentFeeAssignment.objects.filter(student=student_jss2).values_list(
                "fee_structure_id", flat=True
            )
        )
        # JSS 1 Uniform must NOT be assigned to a JSS 2 student
        self.assertNotIn(self.fee_jss1_only.id, assigned_fee_ids)
        # General fees must be assigned
        self.assertIn(self.fee_first_term.id, assigned_fee_ids)
        self.assertIn(self.fee_all_terms.id, assigned_fee_ids)

    def test_bulk_enroll_assigns_fees_to_all_enrolled_students(self):
        s1 = Student.objects.create(
            first_name="Bulk1", last_name="Test", parent_contact="08011223381",
            admission_number="ENR-BULK-1",
        )
        s2 = Student.objects.create(
            first_name="Bulk2", last_name="Test", parent_contact="08011223382",
            admission_number="ENR-BULK-2",
        )

        rows = [
            {"student": s1, "classroom": self.classroom_jss1a, "academic_year": self.academic_year},
            {"student": s2, "classroom": self.classroom_jss1b, "academic_year": self.academic_year},
        ]
        with self.captureOnCommitCallbacks(execute=True):
            EnrollmentService.bulk_enroll(rows)

        s1_fees = set(StudentFeeAssignment.objects.filter(student=s1).values_list("fee_structure_id", flat=True))
        s2_fees = set(StudentFeeAssignment.objects.filter(student=s2).values_list("fee_structure_id", flat=True))

        self.assertIn(self.fee_first_term.id, s1_fees)
        self.assertIn(self.fee_all_terms.id, s1_fees)
        self.assertIn(self.fee_jss1_only.id, s1_fees)

        self.assertIn(self.fee_first_term.id, s2_fees)
        self.assertIn(self.fee_all_terms.id, s2_fees)
        self.assertIn(self.fee_jss1_only.id, s2_fees)


