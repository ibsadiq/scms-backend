from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import Count, Q, Sum
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
    PaymentThrough,
    Receipt,
    StudentFeeAssignment,
)
from finance.services import (
    FinanceReconciliationService,
    PaymentAllocationService,
)

User = get_user_model()


class MultiFeeReportingPhaseDTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.status = "active"
        return super().setup_tenant(tenant)

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)

        self.user = User.objects.create_user(
            email="phase-d-auditor@test.local",
            password="testpassword",
            is_staff=True,
            is_superuser=True,
            is_accountant=True,
            first_name="Finance",
            last_name="Auditor",
        )
        self.client = APIClient(HTTP_HOST=self.domain.domain)
        self.client.force_authenticate(user=self.user)

        # Academic Years
        self.year_2025 = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 1),
            active_year=False,
        )
        self.term_2025_t3 = Term.objects.create(
            name="Third Term",
            academic_year=self.year_2025,
            start_date=date(2026, 4, 15),
            end_date=date(2026, 7, 1),
        )

        self.year_2026 = AcademicYear.objects.create(
            name="2026/2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 7, 1),
            active_year=True,
        )
        self.term_2026_t1 = Term.objects.create(
            name="First Term",
            academic_year=self.year_2026,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 1),
        )
        self.term_2026_t2 = Term.objects.create(
            name="Second Term",
            academic_year=self.year_2026,
            start_date=date(2027, 1, 10),
            end_date=date(2027, 4, 10),
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
            admission_number="GVA/JSS/26/0012",
            classroom=self.classroom,
            parent_contact="08080000001",
        )

        # Fee structures across terms, fee types, and academic years
        self.fee_tuition_prev = FeeStructure.objects.create(
            name="Arrears Tuition",
            amount=Decimal("30000.00"),
            fee_type="Tuition",
            academic_year=self.year_2025,
            term=self.term_2025_t3,
            recurrence=FeeRecurrence.PER_TERM,
            created_by=self.user,
        )
        self.fee_tuition_curr = FeeStructure.objects.create(
            name="Tuition",
            amount=Decimal("100000.00"),
            fee_type="Tuition",
            academic_year=self.year_2026,
            term=self.term_2026_t1,
            recurrence=FeeRecurrence.PER_TERM,
            created_by=self.user,
        )
        self.fee_transport_t2 = FeeStructure.objects.create(
            name="Transport",
            amount=Decimal("25000.00"),
            fee_type="Transport",
            academic_year=self.year_2026,
            term=self.term_2026_t2,
            recurrence=FeeRecurrence.PER_TERM,
            created_by=self.user,
        )
        self.fee_levy_annual = FeeStructure.objects.create(
            name="Development Levy",
            amount=Decimal("20000.00"),
            fee_type="Maintenance",
            academic_year=self.year_2026,
            term=None,
            recurrence=FeeRecurrence.ANNUAL,
            created_by=self.user,
        )

        # Student assignments
        self.assign_prev_tuition = StudentFeeAssignment.objects.create(
            student=self.student,
            fee_structure=self.fee_tuition_prev,
            term=self.term_2025_t3,
            academic_year=self.year_2025,
            amount_owed=Decimal("30000.00"),
            amount_paid=Decimal("0.00"),
        )
        self.assign_curr_tuition = StudentFeeAssignment.objects.create(
            student=self.student,
            fee_structure=self.fee_tuition_curr,
            term=self.term_2026_t1,
            academic_year=self.year_2026,
            amount_owed=Decimal("100000.00"),
            amount_paid=Decimal("0.00"),
        )
        self.assign_t2_transport = StudentFeeAssignment.objects.create(
            student=self.student,
            fee_structure=self.fee_transport_t2,
            term=self.term_2026_t2,
            academic_year=self.year_2026,
            amount_owed=Decimal("25000.00"),
            amount_paid=Decimal("0.00"),
        )
        self.assign_annual_levy = StudentFeeAssignment.objects.create(
            student=self.student,
            fee_structure=self.fee_levy_annual,
            term=self.term_2026_t1,
            academic_year=self.year_2026,
            recurrence=FeeRecurrence.ANNUAL,
            amount_owed=Decimal("20000.00"),
            amount_paid=Decimal("0.00"),
        )

    # -------------------------------------------------------------------------
    # A. Multi-fee receipt counted once in transaction totals
    # -------------------------------------------------------------------------
    def test_a_multi_fee_receipt_counted_once_in_transaction_totals(self):
        receipt = PaymentAllocationService.record_payment_with_allocations(
            receipt_data={
                "student": self.student,
                "payer": "Alhaji Musa",
                "paid_through": PaymentThrough.BANK_TRANSFER,
                "payment_date": date(2026, 9, 5),
            },
            allocations=[
                {"fee_assignment_id": self.assign_curr_tuition.id, "amount": "100000.00"},
                {"fee_assignment_id": self.assign_annual_levy.id, "amount": "20000.00"},
            ],
            actor=self.user,
        )

        response = self.client.get("/api/finance/receipts/summary_stats/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_collected"], 120000.0)
        self.assertEqual(response.data["total_count"], 1)

    # -------------------------------------------------------------------------
    # B. Multi-fee receipt allocation amounts sum correctly
    # -------------------------------------------------------------------------
    def test_b_multi_fee_receipt_allocation_amounts_sum_correctly(self):
        receipt = PaymentAllocationService.record_payment_with_allocations(
            receipt_data={
                "student": self.student,
                "payer": "Alhaji Musa",
                "paid_through": PaymentThrough.CASH,
            },
            allocations=[
                {"fee_assignment_id": self.assign_prev_tuition.id, "amount": "30000.00"},
                {"fee_assignment_id": self.assign_curr_tuition.id, "amount": "60000.00"},
                {"fee_assignment_id": self.assign_annual_levy.id, "amount": "20000.00"},
            ],
            actor=self.user,
        )

        total_alloc = FinanceReconciliationService.get_receipt_allocation_total(receipt.id)
        self.assertEqual(total_alloc, Decimal("110000.00"))
        self.assertEqual(receipt.allocated_amount, Decimal("110000.00"))
        self.assertEqual(receipt.unallocated_amount, Decimal("0.00"))

    # -------------------------------------------------------------------------
    # C. Payment-method breakdown does not multiply receipt total
    # -------------------------------------------------------------------------
    def test_c_payment_method_breakdown_does_not_multiply_receipt_total(self):
        # 1 Receipt for ₦145,000 paid via Bank Transfer across 3 allocations
        PaymentAllocationService.record_payment_with_allocations(
            receipt_data={
                "student": self.student,
                "payer": "Alhaji Musa",
                "paid_through": PaymentThrough.BANK_TRANSFER,
            },
            allocations=[
                {"fee_assignment_id": self.assign_curr_tuition.id, "amount": "100000.00"},
                {"fee_assignment_id": self.assign_t2_transport.id, "amount": "25000.00"},
                {"fee_assignment_id": self.assign_annual_levy.id, "amount": "20000.00"},
            ],
            actor=self.user,
        )

        breakdown = FinanceReconciliationService.get_payment_method_breakdown()
        bank_transfer = next((b for b in breakdown if b["method"] == PaymentThrough.BANK_TRANSFER), None)
        self.assertIsNotNone(bank_transfer)
        # MUST NOT be 3 * 145,000 = 435,000
        self.assertEqual(bank_transfer["total"], Decimal("145000.00"))

    # -------------------------------------------------------------------------
    # D. Fee-type breakdown uses allocation amounts
    # -------------------------------------------------------------------------
    def test_d_fee_type_breakdown_uses_allocation_amounts(self):
        # Receipt of ₦145,000: Tuition (100,000) + Transport (25,000) + Maintenance (20,000)
        PaymentAllocationService.record_payment_with_allocations(
            receipt_data={
                "student": self.student,
                "payer": "Alhaji Musa",
                "paid_through": PaymentThrough.CARD,
            },
            allocations=[
                {"fee_assignment_id": self.assign_curr_tuition.id, "amount": "100000.00"},
                {"fee_assignment_id": self.assign_t2_transport.id, "amount": "25000.00"},
                {"fee_assignment_id": self.assign_annual_levy.id, "amount": "20000.00"},
            ],
            actor=self.user,
        )

        type_breakdown = FinanceReconciliationService.get_fee_type_breakdown()
        type_map = {item["fee_type"]: item["total"] for item in type_breakdown}

        self.assertEqual(type_map.get("Tuition"), Decimal("100000.00"))
        self.assertEqual(type_map.get("Transport"), Decimal("25000.00"))
        self.assertEqual(type_map.get("Maintenance"), Decimal("20000.00"))
        # Sum of breakdown must equal exactly ₦145,000
        self.assertEqual(sum(type_map.values()), Decimal("145000.00"))

    # -------------------------------------------------------------------------
    # E. Academic-year breakdown uses assignment scope
    # -------------------------------------------------------------------------
    def test_e_academic_year_breakdown_uses_assignment_scope(self):
        # One receipt of ₦150,000 spanning two academic years
        PaymentAllocationService.record_payment_with_allocations(
            receipt_data={
                "student": self.student,
                "payer": "Alhaji Musa",
                "paid_through": PaymentThrough.BANK_TRANSFER,
            },
            allocations=[
                {"fee_assignment_id": self.assign_prev_tuition.id, "amount": "30000.00"},
                {"fee_assignment_id": self.assign_curr_tuition.id, "amount": "100000.00"},
                {"fee_assignment_id": self.assign_annual_levy.id, "amount": "20000.00"},
            ],
            actor=self.user,
        )

        year_breakdown = FinanceReconciliationService.get_academic_year_breakdown()
        year_map = {item["academic_year_name"]: item["total"] for item in year_breakdown}

        self.assertEqual(year_map.get("2025/2026"), Decimal("30000.00"))
        self.assertEqual(year_map.get("2026/2027"), Decimal("120000.00"))
        self.assertEqual(sum(year_map.values()), Decimal("150000.00"))

    # -------------------------------------------------------------------------
    # F. Term breakdown uses assignment scope
    # -------------------------------------------------------------------------
    def test_f_term_breakdown_uses_assignment_scope(self):
        # ₦145,000: First Term (100,000) + Second Term (25,000) + Annual Levy (20,000)
        PaymentAllocationService.record_payment_with_allocations(
            receipt_data={
                "student": self.student,
                "payer": "Alhaji Musa",
                "paid_through": PaymentThrough.CASH,
            },
            allocations=[
                {"fee_assignment_id": self.assign_curr_tuition.id, "amount": "100000.00"},
                {"fee_assignment_id": self.assign_t2_transport.id, "amount": "25000.00"},
                {"fee_assignment_id": self.assign_annual_levy.id, "amount": "20000.00"},
            ],
            actor=self.user,
        )

        term_breakdown = FinanceReconciliationService.get_term_breakdown()
        term_map = {item["term_name"]: item["total"] for item in term_breakdown}

        self.assertEqual(term_map.get("First Term"), Decimal("100000.00"))
        self.assertEqual(term_map.get("Second Term"), Decimal("25000.00"))
        self.assertEqual(term_map.get("Annual / One-Time"), Decimal("20000.00"))
        self.assertEqual(sum(term_map.values()), Decimal("145000.00"))

    # -------------------------------------------------------------------------
    # G. Cross-year receipt reports correctly (Comprehensive Section 22 scenario)
    # -------------------------------------------------------------------------
    def test_g_cross_year_receipt_reports_correctly(self):
        receipt = PaymentAllocationService.record_payment_with_allocations(
            receipt_data={
                "student": self.student,
                "payer": "Alhaji Musa",
                "paid_through": PaymentThrough.BANK_TRANSFER,
            },
            allocations=[
                {"fee_assignment_id": self.assign_prev_tuition.id, "amount": "30000.00"},
                {"fee_assignment_id": self.assign_curr_tuition.id, "amount": "100000.00"},
                {"fee_assignment_id": self.assign_annual_levy.id, "amount": "20000.00"},
            ],
            actor=self.user,
        )

        # 1. Receipt total = ₦150,000
        self.assertEqual(receipt.amount, Decimal("150000.00"))

        # 2. Allocation total = ₦150,000
        self.assertEqual(receipt.allocated_amount, Decimal("150000.00"))

        # 3. Student paid total = ₦150,000
        student_audit = FinanceReconciliationService.audit_student(self.student.id)
        self.assertEqual(student_audit["total_paid"], Decimal("150000.00"))
        self.assertTrue(student_audit["is_in_sync"])

        # 4. 2025/2026 report = ₦30,000 & 2026/2027 report = ₦120,000
        year_breakdown = FinanceReconciliationService.get_academic_year_breakdown()
        year_map = {item["academic_year_name"]: item["total"] for item in year_breakdown}
        self.assertEqual(year_map.get("2025/2026"), Decimal("30000.00"))
        self.assertEqual(year_map.get("2026/2027"), Decimal("120000.00"))

        # 5. Tuition report = ₦130,000 & Development Levy = ₦20,000
        fee_types = FinanceReconciliationService.get_fee_type_breakdown()
        fee_map = {item["fee_type"]: item["total"] for item in fee_types}
        self.assertEqual(fee_map.get("Tuition"), Decimal("130000.00"))
        self.assertEqual(fee_map.get("Maintenance"), Decimal("20000.00"))

        # 6. Payment-method sum = ₦150,000
        methods = FinanceReconciliationService.get_payment_method_breakdown()
        method_sum = sum((m["total"] for m in methods), Decimal("0.00"))
        self.assertEqual(method_sum, Decimal("150000.00"))

        # 7. Transaction count = 1, Allocation count = 3
        self.assertEqual(Receipt.objects.count(), 1)
        self.assertEqual(FeePaymentAllocation.objects.count(), 3)

    # -------------------------------------------------------------------------
    # H. Receipt count = 1 while allocation count > 1
    # -------------------------------------------------------------------------
    def test_h_receipt_count_one_while_allocation_count_multiple(self):
        PaymentAllocationService.record_payment_with_allocations(
            receipt_data={
                "student": self.student,
                "payer": "Alhaji Musa",
                "paid_through": PaymentThrough.CASH,
            },
            allocations=[
                {"fee_assignment_id": self.assign_curr_tuition.id, "amount": "50000.00"},
                {"fee_assignment_id": self.assign_annual_levy.id, "amount": "10000.00"},
            ],
            actor=self.user,
        )

        recon = FinanceReconciliationService.reconcile_school_totals()
        self.assertEqual(recon["receipt_count"], 1)
        self.assertEqual(recon["allocation_count"], 2)

    # -------------------------------------------------------------------------
    # I. Legacy unallocated receipt semantics
    # -------------------------------------------------------------------------
    def test_i_legacy_unallocated_receipt_semantics(self):
        # Legacy receipt created directly with ₦100,000
        legacy_receipt = Receipt.objects.create(
            student=self.student,
            payer="Alhaji Musa",
            amount=Decimal("100000.00"),
            paid_through=PaymentThrough.BANK_TRANSFER,
            payment_date=date(2026, 9, 5),
        )

        self.assertEqual(legacy_receipt.allocated_amount, Decimal("0.00"))
        self.assertEqual(legacy_receipt.unallocated_amount, Decimal("100000.00"))

        # Allocate partial amount ₦60,000
        PaymentAllocationService.allocate(
            receipt=legacy_receipt,
            allocations=[
                {"fee_assignment_id": self.assign_curr_tuition.id, "amount": "60000.00"}
            ],
            actor=self.user,
        )

        legacy_receipt.refresh_from_db()
        self.assertEqual(legacy_receipt.allocated_amount, Decimal("60000.00"))
        self.assertEqual(legacy_receipt.unallocated_amount, Decimal("40000.00"))

        # Check summary_stats distinguishes total_received vs total_allocated vs total_unallocated
        response = self.client.get("/api/finance/receipts/summary_stats/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_received"], 100000.0)
        self.assertEqual(response.data["total_allocated"], 60000.0)
        self.assertEqual(response.data["total_unallocated"], 40000.0)

    # -------------------------------------------------------------------------
    # J. Assignment amount_paid equals allocation totals after payment
    # -------------------------------------------------------------------------
    def test_j_assignment_amount_paid_equals_allocation_totals_after_payment(self):
        PaymentAllocationService.record_payment_with_allocations(
            receipt_data={
                "student": self.student,
                "payer": "Alhaji Musa",
                "paid_through": PaymentThrough.CASH,
            },
            allocations=[
                {"fee_assignment_id": self.assign_curr_tuition.id, "amount": "45000.00"},
            ],
            actor=self.user,
        )

        self.assign_curr_tuition.refresh_from_db()
        alloc_total = FinanceReconciliationService.get_assignment_allocation_total(self.assign_curr_tuition.id)

        self.assertEqual(self.assign_curr_tuition.amount_paid, alloc_total)
        audit = FinanceReconciliationService.audit_assignment(self.assign_curr_tuition)
        self.assertTrue(audit["is_in_sync"])
        self.assertEqual(audit["drift"], Decimal("0.00"))

    # -------------------------------------------------------------------------
    # K. Multi-fee receipt reversal restores every assignment
    # -------------------------------------------------------------------------
    def test_k_multi_fee_receipt_reversal_restores_every_assignment(self):
        receipt = PaymentAllocationService.record_payment_with_allocations(
            receipt_data={
                "student": self.student,
                "payer": "Alhaji Musa",
                "paid_through": PaymentThrough.CASH,
            },
            allocations=[
                {"fee_assignment_id": self.assign_curr_tuition.id, "amount": "60000.00"},
                {"fee_assignment_id": self.assign_annual_levy.id, "amount": "10000.00"},
            ],
            actor=self.user,
        )

        self.assign_curr_tuition.refresh_from_db()
        self.assign_annual_levy.refresh_from_db()
        self.assertEqual(self.assign_curr_tuition.amount_paid, Decimal("60000.00"))
        self.assertEqual(self.assign_annual_levy.amount_paid, Decimal("10000.00"))

        # Reverse receipt
        PaymentAllocationService.reverse_receipt(receipt=receipt, actor=self.user)

        self.assign_curr_tuition.refresh_from_db()
        self.assign_annual_levy.refresh_from_db()
        self.assertEqual(self.assign_curr_tuition.amount_paid, Decimal("0.00"))
        self.assertEqual(self.assign_annual_levy.amount_paid, Decimal("0.00"))
        self.assertEqual(Receipt.objects.count(), 0)
        self.assertEqual(FeePaymentAllocation.objects.count(), 0)

    # -------------------------------------------------------------------------
    # L. Reversal leaves unrelated historical payments untouched
    # -------------------------------------------------------------------------
    def test_l_reversal_leaves_unrelated_historical_payments_untouched(self):
        # Receipt 1: Historical payment of ₦40,000 to Tuition
        r1 = PaymentAllocationService.record_payment_with_allocations(
            receipt_data={
                "student": self.student,
                "payer": "Alhaji Musa",
                "paid_through": PaymentThrough.CASH,
            },
            allocations=[
                {"fee_assignment_id": self.assign_curr_tuition.id, "amount": "40000.00"},
            ],
            actor=self.user,
        )

        # Receipt 2: Subsequent payment of ₦30,000 to Tuition and ₦10,000 to Levy
        r2 = PaymentAllocationService.record_payment_with_allocations(
            receipt_data={
                "student": self.student,
                "payer": "Alhaji Musa",
                "paid_through": PaymentThrough.CARD,
            },
            allocations=[
                {"fee_assignment_id": self.assign_curr_tuition.id, "amount": "30000.00"},
                {"fee_assignment_id": self.assign_annual_levy.id, "amount": "10000.00"},
            ],
            actor=self.user,
        )

        self.assign_curr_tuition.refresh_from_db()
        self.assign_annual_levy.refresh_from_db()
        self.assertEqual(self.assign_curr_tuition.amount_paid, Decimal("70000.00"))
        self.assertEqual(self.assign_annual_levy.amount_paid, Decimal("10000.00"))

        # Reverse Receipt 2 only
        PaymentAllocationService.reverse_receipt(receipt=r2, actor=self.user)

        self.assign_curr_tuition.refresh_from_db()
        self.assign_annual_levy.refresh_from_db()
        # Receipt 1's ₦40,000 remains intact!
        self.assertEqual(self.assign_curr_tuition.amount_paid, Decimal("40000.00"))
        self.assertEqual(self.assign_annual_levy.amount_paid, Decimal("0.00"))
        self.assertEqual(Receipt.objects.count(), 1)
        self.assertEqual(Receipt.objects.first().id, r1.id)

    # -------------------------------------------------------------------------
    # M. Partial-payment reversal
    # -------------------------------------------------------------------------
    def test_m_partial_payment_reversal(self):
        # Assignment owed = ₦100,000
        # Receipt A allocates ₦40,000
        ra = PaymentAllocationService.record_payment_with_allocations(
            receipt_data={"student": self.student, "payer": "Payer"},
            allocations=[{"fee_assignment_id": self.assign_curr_tuition.id, "amount": "40000.00"}],
            actor=self.user,
        )
        # Receipt B allocates ₦30,000
        rb = PaymentAllocationService.record_payment_with_allocations(
            receipt_data={"student": self.student, "payer": "Payer"},
            allocations=[{"fee_assignment_id": self.assign_curr_tuition.id, "amount": "30000.00"}],
            actor=self.user,
        )

        # Delete Receipt B
        PaymentAllocationService.reverse_receipt(receipt=rb, actor=self.user)

        self.assign_curr_tuition.refresh_from_db()
        self.assertEqual(self.assign_curr_tuition.amount_paid, Decimal("40000.00"))
        self.assertEqual(self.assign_curr_tuition.balance, Decimal("60000.00"))

    # -------------------------------------------------------------------------
    # N. Audit log records reversal correctly
    # -------------------------------------------------------------------------
    def test_n_audit_log_records_reversal_correctly(self):
        receipt = PaymentAllocationService.record_payment_with_allocations(
            receipt_data={"student": self.student, "payer": "Payer"},
            allocations=[
                {"fee_assignment_id": self.assign_curr_tuition.id, "amount": "20000.00"},
                {"fee_assignment_id": self.assign_annual_levy.id, "amount": "10000.00"},
            ],
            actor=self.user,
        )

        initial_log_count = FinanceAuditLog.objects.count()

        PaymentAllocationService.reverse_receipt(receipt=receipt, actor=self.user)

        self.assertEqual(FinanceAuditLog.objects.count(), initial_log_count + 1)
        reversal_log = FinanceAuditLog.objects.filter(action=AuditAction.PAYMENT_REVERSED).first()
        self.assertIsNotNone(reversal_log)
        self.assertEqual(reversal_log.target_student_id, self.student.id)
        self.assertEqual(reversal_log.metadata["amount"], 30000.0)
        self.assertEqual(reversal_log.metadata["allocations_count"], 2)

    # -------------------------------------------------------------------------
    # O. Waived fees do not appear as collected cash
    # -------------------------------------------------------------------------
    def test_o_waived_fees_do_not_appear_as_collected_cash(self):
        # Waive the transport fee obligation
        self.assign_t2_transport.is_waived = True
        self.assign_t2_transport.save(update_fields=["is_waived"])

        # Check StudentFeeBalanceViewSet response
        response = self.client.get(f"/api/finance/student-balance/{self.student.id}/?term_id={self.term_2026_t2.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(response.data["amount_paid"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(response.data["balance"])), Decimal("0.00"))

        # Check FinanceDashboardSummaryView does not count waived fees in expected or collected
        dashboard_response = self.client.get(f"/api/finance/dashboard/summary/?term_id={self.term_2026_t2.id}")
        self.assertEqual(dashboard_response.status_code, status.HTTP_200_OK)
        self.assertEqual(dashboard_response.data["total_collected"], 0.0)
        self.assertEqual(dashboard_response.data["total_expected"], 0.0)

    # -------------------------------------------------------------------------
    # P. No receipt-total multiplication through allocation joins
    # -------------------------------------------------------------------------
    def test_p_no_receipt_total_multiplication_through_allocation_joins(self):
        # Single receipt of ₦120,000 with 2 allocations
        receipt = PaymentAllocationService.record_payment_with_allocations(
            receipt_data={"student": self.student, "payer": "Payer"},
            allocations=[
                {"fee_assignment_id": self.assign_curr_tuition.id, "amount": "100000.00"},
                {"fee_assignment_id": self.assign_annual_levy.id, "amount": "20000.00"},
            ],
            actor=self.user,
        )

        # Dangerous SQL join query simulated:
        # Joining Receipt to fee_allocations would return 2 rows for the receipt!
        joined_qs = Receipt.objects.filter(fee_allocations__isnull=False)
        self.assertEqual(joined_qs.count(), 2)  # Notice: raw count without distinct is 2!

        # Safe transaction total query via distinct subquery
        safe_total = Receipt.objects.filter(
            id__in=joined_qs.values("id")
        ).aggregate(total=Sum("amount"))["total"]

        # MUST be ₦120,000, NOT ₦240,000
        self.assertEqual(safe_total, Decimal("120000.00"))

        # Reconcile school totals also returns ₦120,000
        recon = FinanceReconciliationService.reconcile_school_totals()
        self.assertEqual(recon["total_received"], Decimal("120000.00"))
        self.assertEqual(recon["total_allocated"], Decimal("120000.00"))
        self.assertEqual(recon["receipt_count"], 1)
        self.assertEqual(recon["allocation_count"], 2)
