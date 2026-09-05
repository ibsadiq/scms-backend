from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from school.testcases import TenantTestCase

from academic.models import ClassRoom, GradeLevel, Student
from administration.models import AcademicYear, Term
from finance.models import (
    AuditAction,
    FeePaymentAllocation,
    FeeRecurrence,
    FeeStructure,
    FinanceAuditLog,
    Receipt,
    StudentFeeAssignment,
)
from finance.services import PaymentAllocationService


User = get_user_model()


class MultiFeePaymentPhaseATests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.status = "active"
        return super().setup_tenant(tenant)

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)

        self.user = User.objects.create_user(
            email="phase-a-accountant@test.local",
            password="testpassword",
            is_staff=True,
            is_superuser=True,
            is_accountant=True,
            first_name="Finance",
            last_name="Accountant",
        )
        self.client = APIClient(HTTP_HOST=self.domain.domain)
        self.client.force_authenticate(user=self.user)

        self.year = AcademicYear.objects.create(
            name="2028/2029",
            start_date=date(2028, 9, 1),
            end_date=date(2029, 7, 1),
            active_year=True,
        )
        self.term_1 = Term.objects.create(
            name="First Term",
            academic_year=self.year,
            start_date=date(2028, 9, 1),
            end_date=date(2028, 12, 1),
        )
        self.term_2 = Term.objects.create(
            name="Second Term",
            academic_year=self.year,
            start_date=date(2029, 1, 10),
            end_date=date(2029, 4, 10),
        )
        self.grade_jss1 = GradeLevel.objects.create(
            system_code="JSS_1", section="JSS", default_name="JSS 1", sequence_order=1
        )
        self.classroom = ClassRoom.objects.create(
            name="JSS 1A", grade_level=self.grade_jss1, capacity=35
        )

        self.student = Student.objects.create(
            first_name="Ibrahim",
            last_name="Musa",
            admission_number="GVA/JSS/28/0012",
            classroom=self.classroom,
            parent_contact="08080000001",
        )
        self.other_student = Student.objects.create(
            first_name="Fatima",
            last_name="Ali",
            admission_number="GVA/JSS/28/0013",
            classroom=self.classroom,
            parent_contact="08080000002",
        )

        # 3 distinct fee structures
        self.fee_tuition_t1 = FeeStructure.objects.create(
            name="Tuition",
            amount=Decimal("120000.00"),
            fee_type="Tuition",
            academic_year=self.year,
            term=self.term_1,
            created_by=self.user,
        )
        self.fee_ict_t1 = FeeStructure.objects.create(
            name="ICT Fee",
            amount=Decimal("15000.00"),
            fee_type="Other",
            academic_year=self.year,
            term=self.term_1,
            created_by=self.user,
        )
        self.fee_levy_annual = FeeStructure.objects.create(
            name="Development Levy",
            amount=Decimal("25000.00"),
            fee_type="Maintenance",
            recurrence=FeeRecurrence.ANNUAL,
            academic_year=self.year,
            term=None,
            created_by=self.user,
        )
        self.fee_tuition_t2 = FeeStructure.objects.create(
            name="Second Term Tuition",
            amount=Decimal("120000.00"),
            fee_type="Tuition",
            academic_year=self.year,
            term=self.term_2,
            created_by=self.user,
        )

        # Assign fees to students
        self.assign_tuition_t1 = StudentFeeAssignment.objects.create(
            student=self.student,
            fee_structure=self.fee_tuition_t1,
            term=self.term_1,
            academic_year=self.year,
            amount_owed=Decimal("120000.00"),
        )
        self.assign_ict_t1 = StudentFeeAssignment.objects.create(
            student=self.student,
            fee_structure=self.fee_ict_t1,
            term=self.term_1,
            academic_year=self.year,
            amount_owed=Decimal("15000.00"),
        )
        self.assign_levy_annual = StudentFeeAssignment.objects.create(
            student=self.student,
            fee_structure=self.fee_levy_annual,
            term=self.term_1,
            academic_year=self.year,
            amount_owed=Decimal("25000.00"),
        )
        self.assign_tuition_t2 = StudentFeeAssignment.objects.create(
            student=self.student,
            fee_structure=self.fee_tuition_t2,
            term=self.term_2,
            academic_year=self.year,
            amount_owed=Decimal("120000.00"),
        )

        # Other student's assignment
        self.other_assign_tuition = StudentFeeAssignment.objects.create(
            student=self.other_student,
            fee_structure=self.fee_tuition_t1,
            term=self.term_1,
            academic_year=self.year,
            amount_owed=Decimal("120000.00"),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # A. Multi-fee happy path via Service
    # ──────────────────────────────────────────────────────────────────────────
    def test_multi_fee_service_happy_path(self):
        allocations = [
            {"fee_assignment": self.assign_tuition_t1.pk, "amount": "120000.00"},
            {"fee_assignment": self.assign_ict_t1.pk, "amount": "15000.00"},
            {"fee_assignment": self.assign_levy_annual.pk, "amount": "25000.00"},
        ]
        receipt = PaymentAllocationService.record_payment_with_allocations(
            receipt_data={
                "payer": "Alhaji Musa",
                "paid_through": "Bank Transfer",
                "payment_date": date(2028, 9, 15),
                "reference_number": "TRF-HAPPY-001",
                "remarks": "Complete settlement",
            },
            allocations=allocations,
            actor=self.user,
        )

        self.assertEqual(receipt.amount, Decimal("160000.00"))
        self.assertEqual(receipt.allocated_amount, Decimal("160000.00"))
        self.assertEqual(receipt.unallocated_amount, Decimal("0.00"))
        self.assertEqual(receipt.fee_allocations.count(), 3)
        self.assertIsNotNone(receipt.receipt_number)

        self.assign_tuition_t1.refresh_from_db()
        self.assign_ict_t1.refresh_from_db()
        self.assign_levy_annual.refresh_from_db()

        self.assertEqual(self.assign_tuition_t1.amount_paid, Decimal("120000.00"))
        self.assertEqual(self.assign_tuition_t1.balance, Decimal("0.00"))
        self.assertEqual(self.assign_tuition_t1.payment_status, "Paid")

        self.assertEqual(self.assign_ict_t1.amount_paid, Decimal("15000.00"))
        self.assertEqual(self.assign_ict_t1.balance, Decimal("0.00"))

        self.assertEqual(self.assign_levy_annual.amount_paid, Decimal("25000.00"))
        self.assertEqual(self.assign_levy_annual.balance, Decimal("0.00"))

        # Verify audit log
        audit = FinanceAuditLog.objects.filter(
            action=AuditAction.PAYMENT_RECORDED, target_student=self.student
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.metadata["allocations_count"], 3)
        self.assertEqual(audit.metadata["amount"], 160000.00)

    # ──────────────────────────────────────────────────────────────────────────
    # B. Mixed full + partial allocations
    # ──────────────────────────────────────────────────────────────────────────
    def test_mixed_full_and_partial_allocations(self):
        allocations = [
            {"fee_assignment": self.assign_tuition_t1.pk, "amount": "70000.00"},  # Partial (leaves 50,000)
            {"fee_assignment": self.assign_ict_t1.pk, "amount": "15000.00"},      # Full
        ]
        receipt = PaymentAllocationService.record_payment_with_allocations(
            receipt_data={"payer": "Ibrahim Musa", "paid_through": "Cash"},
            allocations=allocations,
            actor=self.user,
        )
        self.assertEqual(receipt.amount, Decimal("85000.00"))

        self.assign_tuition_t1.refresh_from_db()
        self.assign_ict_t1.refresh_from_db()

        self.assertEqual(self.assign_tuition_t1.amount_paid, Decimal("70000.00"))
        self.assertEqual(self.assign_tuition_t1.balance, Decimal("50000.00"))
        self.assertEqual(self.assign_tuition_t1.payment_status, "Partial")

        self.assertEqual(self.assign_ict_t1.amount_paid, Decimal("15000.00"))
        self.assertEqual(self.assign_ict_t1.balance, Decimal("0.00"))
        self.assertEqual(self.assign_ict_t1.payment_status, "Paid")

    # ──────────────────────────────────────────────────────────────────────────
    # C. Duplicate assignment rejected
    # ──────────────────────────────────────────────────────────────────────────
    def test_duplicate_assignment_in_allocations_rejected(self):
        allocations = [
            {"fee_assignment": self.assign_tuition_t1.pk, "amount": "30000.00"},
            {"fee_assignment": self.assign_tuition_t1.pk, "amount": "20000.00"},
        ]
        with self.assertRaises(ValidationError) as ctx:
            PaymentAllocationService.record_payment_with_allocations(
                receipt_data={"payer": "Test"},
                allocations=allocations,
                actor=self.user,
            )
        self.assertIn("Duplicate fee assignment ID", str(ctx.exception))

    # ──────────────────────────────────────────────────────────────────────────
    # D. Different students rejected
    # ──────────────────────────────────────────────────────────────────────────
    def test_cross_student_allocations_rejected(self):
        allocations = [
            {"fee_assignment": self.assign_tuition_t1.pk, "amount": "50000.00"},
            {"fee_assignment": self.other_assign_tuition.pk, "amount": "50000.00"},
        ]
        with self.assertRaises(ValidationError) as ctx:
            PaymentAllocationService.record_payment_with_allocations(
                receipt_data={"payer": "Test"},
                allocations=allocations,
                actor=self.user,
            )
        self.assertIn("All fee allocations must belong to the same student", str(ctx.exception))

    # ──────────────────────────────────────────────────────────────────────────
    # E. Allocation exceeds balance rejected
    # ──────────────────────────────────────────────────────────────────────────
    def test_allocation_exceeding_balance_rejected(self):
        allocations = [
            {"fee_assignment": self.assign_ict_t1.pk, "amount": "20000.00"},  # Balance is 15,000
        ]
        with self.assertRaises(ValidationError) as ctx:
            PaymentAllocationService.record_payment_with_allocations(
                receipt_data={"payer": "Test"},
                allocations=allocations,
                actor=self.user,
            )
        self.assertIn("balance is only ₦15,000.00", str(ctx.exception))

    # ──────────────────────────────────────────────────────────────────────────
    # F. Zero amount rejected
    # ──────────────────────────────────────────────────────────────────────────
    def test_zero_amount_allocation_rejected(self):
        allocations = [
            {"fee_assignment": self.assign_tuition_t1.pk, "amount": "0.00"},
        ]
        with self.assertRaises(ValidationError) as ctx:
            PaymentAllocationService.record_payment_with_allocations(
                receipt_data={"payer": "Test"},
                allocations=allocations,
                actor=self.user,
            )
        self.assertIn("Allocation amount for assignment", str(ctx.exception))

    # ──────────────────────────────────────────────────────────────────────────
    # G. Negative amount rejected
    # ──────────────────────────────────────────────────────────────────────────
    def test_negative_amount_allocation_rejected(self):
        allocations = [
            {"fee_assignment": self.assign_tuition_t1.pk, "amount": "-500.00"},
        ]
        with self.assertRaises(ValidationError) as ctx:
            PaymentAllocationService.record_payment_with_allocations(
                receipt_data={"payer": "Test"},
                allocations=allocations,
                actor=self.user,
            )
        self.assertIn("must be positive", str(ctx.exception))

    # ──────────────────────────────────────────────────────────────────────────
    # H. Empty allocations rejected
    # ──────────────────────────────────────────────────────────────────────────
    def test_empty_allocations_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            PaymentAllocationService.record_payment_with_allocations(
                receipt_data={"payer": "Test"},
                allocations=[],
                actor=self.user,
            )
        self.assertIn("At least one fee allocation is required", str(ctx.exception))

    # ──────────────────────────────────────────────────────────────────────────
    # I. Atomic rollback on partial failure
    # ──────────────────────────────────────────────────────────────────────────
    def test_atomic_rollback_on_failure(self):
        receipt_count_before = Receipt.objects.count()
        alloc_count_before = FeePaymentAllocation.objects.count()

        allocations = [
            {"fee_assignment": self.assign_tuition_t1.pk, "amount": "50000.00"},  # valid
            {"fee_assignment": self.assign_ict_t1.pk, "amount": "99999.00"},      # invalid (exceeds balance)
        ]

        with self.assertRaises(ValidationError):
            PaymentAllocationService.record_payment_with_allocations(
                receipt_data={"payer": "Test"},
                allocations=allocations,
                actor=self.user,
            )

        self.assertEqual(Receipt.objects.count(), receipt_count_before)
        self.assertEqual(FeePaymentAllocation.objects.count(), alloc_count_before)

        self.assign_tuition_t1.refresh_from_db()
        self.assign_ict_t1.refresh_from_db()
        self.assertEqual(self.assign_tuition_t1.amount_paid, Decimal("0.00"))
        self.assertEqual(self.assign_ict_t1.amount_paid, Decimal("0.00"))

    # ──────────────────────────────────────────────────────────────────────────
    # J. Same-term receipt term resolution
    # ──────────────────────────────────────────────────────────────────────────
    def test_same_term_allocations_resolves_receipt_term(self):
        allocations = [
            {"fee_assignment": self.assign_tuition_t1.pk, "amount": "50000.00"},
            {"fee_assignment": self.assign_ict_t1.pk, "amount": "10000.00"},
        ]
        receipt = PaymentAllocationService.record_payment_with_allocations(
            receipt_data={"payer": "Test"},
            allocations=allocations,
            actor=self.user,
        )
        self.assertEqual(receipt.term, self.term_1)

    # ──────────────────────────────────────────────────────────────────────────
    # K. Cross-term receipt term resolution (Receipt.term = None)
    # ──────────────────────────────────────────────────────────────────────────
    def test_cross_term_allocations_sets_receipt_term_null(self):
        allocations = [
            {"fee_assignment": self.assign_tuition_t1.pk, "amount": "50000.00"},  # Term 1
            {"fee_assignment": self.assign_tuition_t2.pk, "amount": "50000.00"},  # Term 2
        ]
        receipt = PaymentAllocationService.record_payment_with_allocations(
            receipt_data={"payer": "Test"},
            allocations=allocations,
            actor=self.user,
        )
        self.assertIsNone(receipt.term)
        self.assertEqual(receipt.amount, Decimal("100000.00"))
        self.assertEqual(receipt.fee_allocations.count(), 2)

    # ──────────────────────────────────────────────────────────────────────────
    # L. Waived assignment rejected
    # ──────────────────────────────────────────────────────────────────────────
    def test_waived_assignment_rejected(self):
        self.assign_ict_t1.waive_fee(reason="Scholarship", waived_by=self.user)
        self.assertTrue(self.assign_ict_t1.is_waived)
        self.assertEqual(self.assign_ict_t1.balance, Decimal("0.00"))

        allocations = [
            {"fee_assignment": self.assign_ict_t1.pk, "amount": "5000.00"},
        ]
        with self.assertRaises(ValidationError) as ctx:
            PaymentAllocationService.record_payment_with_allocations(
                receipt_data={"payer": "Test"},
                allocations=allocations,
                actor=self.user,
            )
        self.assertIn("Cannot allocate payment to waived fee", str(ctx.exception))

    # ──────────────────────────────────────────────────────────────────────────
    # M. Prior partial payment uses current balance
    # ──────────────────────────────────────────────────────────────────────────
    def test_prior_partial_payment_validates_against_current_balance(self):
        # Apply initial ₦40,000 allocation
        initial_receipt = Receipt.objects.create(
            student=self.student,
            payer="Initial",
            amount=Decimal("40000.00"),
            received_by=self.user,
        )
        FeePaymentAllocation.objects.create(
            receipt=initial_receipt,
            fee_assignment=self.assign_tuition_t1,
            amount=Decimal("40000.00"),
            allocated_by=self.user,
        )
        self.assign_tuition_t1.refresh_from_db()
        self.assertEqual(self.assign_tuition_t1.amount_paid, Decimal("40000.00"))
        self.assertEqual(self.assign_tuition_t1.balance, Decimal("80000.00"))

        # Paying remaining ₦80,000 succeeds
        second_receipt = PaymentAllocationService.record_payment_with_allocations(
            receipt_data={"payer": "Second Payment"},
            allocations=[{"fee_assignment": self.assign_tuition_t1.pk, "amount": "80000.00"}],
            actor=self.user,
        )
        self.assign_tuition_t1.refresh_from_db()
        self.assertEqual(self.assign_tuition_t1.amount_paid, Decimal("120000.00"))
        self.assertEqual(self.assign_tuition_t1.balance, Decimal("0.00"))
        self.assertEqual(self.assign_tuition_t1.payment_status, "Paid")

        # Third payment fails because balance is now 0
        with self.assertRaises(ValidationError):
            PaymentAllocationService.record_payment_with_allocations(
                receipt_data={"payer": "Overpay"},
                allocations=[{"fee_assignment": self.assign_tuition_t1.pk, "amount": "1000.00"}],
                actor=self.user,
            )

    # ──────────────────────────────────────────────────────────────────────────
    # N. API POST /api/finance/receipts/ with nested allocations (Happy Path)
    # ──────────────────────────────────────────────────────────────────────────
    def test_api_atomic_multi_fee_payment_happy_path(self):
        url = "/api/finance/receipts/"
        payload = {
            "student": self.student.id,
            "payer": "Alhaji Musa",
            "paid_through": "Bank Transfer",
            "payment_date": "2028-09-18",
            "reference_number": "API-TRF-001",
            "remarks": "API Multi-fee payment",
            "allocations": [
                {"fee_assignment": self.assign_tuition_t1.id, "amount": "100000.00"},
                {"fee_assignment": self.assign_ict_t1.id, "amount": "15000.00"},
            ],
        }

        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, getattr(response, "data", response.content))

        data = response.data
        self.assertEqual(Decimal(str(data["amount"])), Decimal("115000.00"))
        self.assertEqual(Decimal(str(data["allocated_amount"])), Decimal("115000.00"))
        self.assertEqual(Decimal(str(data["unallocated_amount"])), Decimal("0.00"))
        self.assertEqual(len(data["fee_allocations"]), 2)

        # Check nested allocation fields
        alloc_map = {a["fee_assignment"]: a for a in data["fee_allocations"]}
        self.assertIn(self.assign_tuition_t1.id, alloc_map)
        self.assertIn(self.assign_ict_t1.id, alloc_map)

        alloc_tuition = alloc_map[self.assign_tuition_t1.id]
        self.assertEqual(alloc_tuition["fee_structure_name"], "Tuition")
        self.assertEqual(Decimal(str(alloc_tuition["amount"])), Decimal("100000.00"))
        self.assertEqual(Decimal(str(alloc_tuition["remaining_balance"])), Decimal("20000.00"))
        self.assertEqual(alloc_tuition["academic_year_name"], "2028/2029")
        self.assertEqual(alloc_tuition["term_name"], "First Term")

        alloc_ict = alloc_map[self.assign_ict_t1.id]
        self.assertEqual(alloc_ict["fee_structure_name"], "ICT Fee")
        self.assertEqual(Decimal(str(alloc_ict["amount"])), Decimal("15000.00"))
        self.assertEqual(Decimal(str(alloc_ict["remaining_balance"])), Decimal("0.00"))

    # ──────────────────────────────────────────────────────────────────────────
    # O. API POST /api/finance/receipts/ validation failure (Bad Request)
    # ──────────────────────────────────────────────────────────────────────────
    def test_api_atomic_multi_fee_payment_validation_error(self):
        url = "/api/finance/receipts/"
        payload = {
            "student": self.student.id,
            "allocations": [
                {"fee_assignment": self.assign_ict_t1.id, "amount": "999999.00"},
            ],
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, getattr(response, "data", response.content))

    # ──────────────────────────────────────────────────────────────────────────
    # P. Legacy receipt creation without allocations continues to work
    # ──────────────────────────────────────────────────────────────────────────
    def test_api_legacy_receipt_create_without_allocations(self):
        url = "/api/finance/receipts/"
        payload = {
            "student": self.student.id,
            "payer": "Legacy Payer",
            "amount": "50000.00",
            "paid_through": "Cash",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, getattr(response, "data", response.content))
        data = response.data
        self.assertEqual(Decimal(str(data["amount"])), Decimal("50000.00"))
        self.assertEqual(Decimal(str(data["unallocated_amount"])), Decimal("50000.00"))
        self.assertEqual(len(data["fee_allocations"]), 0)

    # ──────────────────────────────────────────────────────────────────────────
    # Q. Existing allocate_to_fees endpoint continues to work
    # ──────────────────────────────────────────────────────────────────────────
    def test_api_legacy_allocate_to_fees_endpoint_works(self):
        # 1. Create bare receipt
        receipt = Receipt.objects.create(
            student=self.student,
            payer="Manual Payer",
            amount=Decimal("30000.00"),
            received_by=self.user,
        )
        # 2. Call allocate_to_fees
        url = f"/api/finance/receipts/{receipt.pk}/allocate_to_fees/"
        payload = {
            "allocations": [
                {"fee_assignment_id": self.assign_ict_t1.id, "amount": "15000.00"}
            ]
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assign_ict_t1.refresh_from_db()
        self.assertEqual(self.assign_ict_t1.amount_paid, Decimal("15000.00"))
        receipt.refresh_from_db()
        self.assertEqual(receipt.unallocated_amount, Decimal("15000.00"))
