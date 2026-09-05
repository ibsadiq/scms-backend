from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from rest_framework import status
from rest_framework.test import APIClient
from school.testcases import TenantTestCase

from academic.models import ClassRoom, GradeLevel, Student
from administration.models import AcademicYear, Term
from finance.models import (
    FeePaymentAllocation,
    FeeRecurrence,
    FeeStructure,
    Receipt,
    StudentFeeAssignment,
)
from finance.serializers import FeePaymentAllocationSerializer, ReceiptSerializer
from finance.tasks import (
    build_receipt_html,
    get_fee_academic_year_label,
    get_fee_scope_label,
    render_receipt_pdf,
)

User = get_user_model()


class ConsolidatedReceiptPhaseBTests(TenantTestCase):
    """
    Test suite for Phase B: Consolidated Receipt PDF & Presentation Hardening.
    Validates receipt rendering semantics, academic scope labels, header term integrity,
    legacy fallback, metadata safety, and serializer read enhancements.
    """

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.status = "active"
        return super().setup_tenant(tenant)

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)

        self.user = User.objects.create_user(
            email="phase-b-accountant@test.local",
            password="testpassword",
            is_staff=True,
            is_superuser=True,
            is_accountant=True,
            first_name="Finance",
            last_name="Officer",
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

        # 1. PER_TERM Fee (First Term)
        self.fee_tuition_t1 = FeeStructure.objects.create(
            name="Tuition",
            amount=Decimal("120000.00"),
            fee_type="Tuition",
            recurrence=FeeRecurrence.PER_TERM,
            academic_year=self.year,
            term=self.term_1,
            created_by=self.user,
        )
        self.assignment_tuition_t1 = StudentFeeAssignment.objects.create(
            student=self.student,
            fee_structure=self.fee_tuition_t1,
            academic_year=self.year,
            term=self.term_1,
            recurrence=FeeRecurrence.PER_TERM,
            amount_owed=Decimal("120000.00"),
            amount_paid=Decimal("0.00"),
        )

        # 2. PER_TERM Fee (Second Term)
        self.fee_books_t2 = FeeStructure.objects.create(
            name="Books",
            amount=Decimal("25000.00"),
            fee_type="Books",
            recurrence=FeeRecurrence.PER_TERM,
            academic_year=self.year,
            term=self.term_2,
            created_by=self.user,
        )
        self.assignment_books_t2 = StudentFeeAssignment.objects.create(
            student=self.student,
            fee_structure=self.fee_books_t2,
            academic_year=self.year,
            term=self.term_2,
            recurrence=FeeRecurrence.PER_TERM,
            amount_owed=Decimal("25000.00"),
            amount_paid=Decimal("0.00"),
        )

        # 3. ANNUAL Fee
        self.fee_dev_levy = FeeStructure.objects.create(
            name="Development Levy",
            amount=Decimal("40000.00"),
            fee_type="Maintenance",
            recurrence=FeeRecurrence.ANNUAL,
            academic_year=self.year,
            term=None,
            logical_fee_key="dev-levy",
            created_by=self.user,
        )
        self.assignment_dev_levy = StudentFeeAssignment.objects.create(
            student=self.student,
            fee_structure=self.fee_dev_levy,
            academic_year=self.year,
            term=self.term_1,
            recurrence=FeeRecurrence.ANNUAL,
            logical_fee_key="dev-levy",
            amount_owed=Decimal("40000.00"),
            amount_paid=Decimal("0.00"),
        )

        # 4. ONE_TIME Fee
        self.fee_admission = FeeStructure.objects.create(
            name="Admission Fee",
            amount=Decimal("50000.00"),
            fee_type="Other",
            recurrence=FeeRecurrence.ONE_TIME,
            academic_year=self.year,
            term=None,
            logical_fee_key="adm-fee",
            created_by=self.user,
        )
        self.assignment_admission = StudentFeeAssignment.objects.create(
            student=self.student,
            fee_structure=self.fee_admission,
            academic_year=self.year,
            term=self.term_1,
            recurrence=FeeRecurrence.ONE_TIME,
            logical_fee_key="adm-fee",
            amount_owed=Decimal("50000.00"),
            amount_paid=Decimal("0.00"),
        )

    # -------------------------------------------------------------------------
    # Helper Unit Tests
    # -------------------------------------------------------------------------

    def test_scope_label_helper(self):
        """Helper correctly resolves concrete term, Annual, One-Time, and fallbacks."""
        self.assertEqual(get_fee_scope_label(self.assignment_tuition_t1), "First Term")
        self.assertEqual(get_fee_scope_label(self.assignment_books_t2), "Second Term")
        self.assertEqual(get_fee_scope_label(self.assignment_dev_levy), "Annual")
        self.assertEqual(get_fee_scope_label(self.assignment_admission), "One-Time")
        self.assertEqual(get_fee_scope_label(None), "—")

    def test_academic_year_label_helper(self):
        """Helper correctly resolves academic year from assignment, term, or structure."""
        self.assertEqual(get_fee_academic_year_label(self.assignment_tuition_t1), "2028/2029")
        self.assertEqual(get_fee_academic_year_label(self.assignment_dev_levy), "2028/2029")
        self.assertEqual(get_fee_academic_year_label(None), "—")

    # -------------------------------------------------------------------------
    # Criteria A, H, I: Multi-allocation receipt renders all fee rows & total
    # -------------------------------------------------------------------------

    def test_multi_allocation_receipt_renders_all_fee_rows(self):
        """Multi-allocation receipt renders each allocation row with accurate amounts and total."""
        receipt = Receipt.objects.create(
            student=self.student,
            amount=Decimal("185000.00"),
            paid_through="Bank Transfer",
            term=None,
            payment_date=date(2028, 9, 15),
            payer="Alhaji Musa",
            status="Completed",
            reference_number="REF-MULTI-100",
            received_by=self.user,
        )
        FeePaymentAllocation.objects.create(
            receipt=receipt,
            fee_assignment=self.assignment_tuition_t1,
            amount=Decimal("120000.00"),
            allocated_by=self.user,
        )
        FeePaymentAllocation.objects.create(
            receipt=receipt,
            fee_assignment=self.assignment_books_t2,
            amount=Decimal("25000.00"),
            allocated_by=self.user,
        )
        FeePaymentAllocation.objects.create(
            receipt=receipt,
            fee_assignment=self.assignment_dev_levy,
            amount=Decimal("40000.00"),
            allocated_by=self.user,
        )

        html = build_receipt_html(receipt)

        # Line items present
        self.assertIn("Tuition", html)
        self.assertIn("Books", html)
        self.assertIn("Development Levy", html)

        # Academic scopes present
        self.assertIn("First Term", html)
        self.assertIn("Second Term", html)
        self.assertIn("Annual", html)
        self.assertIn("2028/2029", html)

        # Allocation amounts formatted in Naira
        self.assertIn("120,000.00", html)
        self.assertIn("25,000.00", html)
        self.assertIn("40,000.00", html)

        # Total paid equals Receipt.amount
        self.assertIn("185,000.00", html)

    # -------------------------------------------------------------------------
    # Criteria B: Allocation amount shown, not full fee amount
    # -------------------------------------------------------------------------

    def test_allocation_amount_shown_not_full_fee_amount(self):
        """For a partial payment, the receipt line shows allocation amount, not the owed amount."""
        # Tuition owed is ₦120,000, but partial payment is only ₦50,000
        receipt = Receipt.objects.create(
            student=self.student,
            amount=Decimal("50000.00"),
            paid_through="Cash",
            term=self.term_1,
            payment_date=date(2028, 9, 20),
            payer="Alhaji Musa",
        )
        FeePaymentAllocation.objects.create(
            receipt=receipt,
            fee_assignment=self.assignment_tuition_t1,
            amount=Decimal("50000.00"),
            allocated_by=self.user,
        )

        html = build_receipt_html(receipt)

        self.assertIn("50,000.00", html)
        # 120,000.00 should NOT appear as an allocation amount in the table
        # (check that table td amount has 50,000.00)
        self.assertIn("&#8358;50,000.00", html)

    # -------------------------------------------------------------------------
    # Criteria C: Same-term receipt displays correct term
    # -------------------------------------------------------------------------

    def test_same_term_receipt_displays_correct_header_term(self):
        """When receipt and all allocations genuinely belong to the same term, header displays it."""
        receipt = Receipt.objects.create(
            student=self.student,
            amount=Decimal("120000.00"),
            paid_through="POS",
            term=self.term_1,
            payment_date=date(2028, 9, 20),
        )
        FeePaymentAllocation.objects.create(
            receipt=receipt,
            fee_assignment=self.assignment_tuition_t1,
            amount=Decimal("120000.00"),
            allocated_by=self.user,
        )

        html = build_receipt_html(receipt)
        self.assertIn("Term: First Term", html)
        self.assertNotIn("Multiple / Mixed", html)

    # -------------------------------------------------------------------------
    # Criteria D: Mixed-term receipt does not display misleading single header term
    # -------------------------------------------------------------------------

    def test_mixed_term_receipt_displays_multiple_mixed_header(self):
        """When allocations span multiple terms or annual fees, header displays Multiple / Mixed."""
        receipt = Receipt.objects.create(
            student=self.student,
            amount=Decimal("145000.00"),
            paid_through="Bank Transfer",
            term=None,  # Mixed receipt has no single term
            payment_date=date(2028, 9, 22),
        )
        FeePaymentAllocation.objects.create(
            receipt=receipt,
            fee_assignment=self.assignment_tuition_t1,
            amount=Decimal("120000.00"),
            allocated_by=self.user,
        )
        FeePaymentAllocation.objects.create(
            receipt=receipt,
            fee_assignment=self.assignment_books_t2,
            amount=Decimal("25000.00"),
            allocated_by=self.user,
        )

        html = build_receipt_html(receipt)
        self.assertIn("Term: Multiple / Mixed", html)
        self.assertNotIn("Term: First Term", html)
        self.assertNotIn("Term: Second Term", html)

    def test_contradictory_term_on_receipt_falls_back_to_mixed(self):
        """If receipt.term is set but allocations have mixed terms, header shows Multiple / Mixed."""
        receipt = Receipt.objects.create(
            student=self.student,
            amount=Decimal("145000.00"),
            paid_through="Bank Transfer",
            term=self.term_1,  # Inaccurately set
            payment_date=date(2028, 9, 22),
        )
        FeePaymentAllocation.objects.create(
            receipt=receipt,
            fee_assignment=self.assignment_tuition_t1,
            amount=Decimal("120000.00"),
            allocated_by=self.user,
        )
        FeePaymentAllocation.objects.create(
            receipt=receipt,
            fee_assignment=self.assignment_books_t2,
            amount=Decimal("25000.00"),
            allocated_by=self.user,
        )

        html = build_receipt_html(receipt)
        self.assertIn("Term: Multiple / Mixed", html)

    # -------------------------------------------------------------------------
    # Criteria E, F, G: Recurrence rendering (Annual, One-Time, PER_TERM)
    # -------------------------------------------------------------------------

    def test_annual_fee_renders_annual(self):
        """Annual fee renders 'Annual' in the academic scope column."""
        receipt = Receipt.objects.create(
            student=self.student,
            amount=Decimal("40000.00"),
            paid_through="Bank Transfer",
            term=None,
        )
        FeePaymentAllocation.objects.create(
            receipt=receipt,
            fee_assignment=self.assignment_dev_levy,
            amount=Decimal("40000.00"),
        )

        html = build_receipt_html(receipt)
        self.assertIn("Annual", html)

    def test_one_time_fee_renders_one_time(self):
        """One-time fee renders 'One-Time' in the academic scope column."""
        receipt = Receipt.objects.create(
            student=self.student,
            amount=Decimal("50000.00"),
            paid_through="Bank Transfer",
            term=None,
        )
        FeePaymentAllocation.objects.create(
            receipt=receipt,
            fee_assignment=self.assignment_admission,
            amount=Decimal("50000.00"),
        )

        html = build_receipt_html(receipt)
        self.assertIn("One-Time", html)

    def test_specific_per_term_renders_actual_term(self):
        """PER_TERM fee with a concrete term renders the actual term name."""
        receipt = Receipt.objects.create(
            student=self.student,
            amount=Decimal("120000.00"),
            paid_through="Bank Transfer",
            term=self.term_1,
        )
        FeePaymentAllocation.objects.create(
            receipt=receipt,
            fee_assignment=self.assignment_tuition_t1,
            amount=Decimal("120000.00"),
        )

        html = build_receipt_html(receipt)
        self.assertIn("First Term", html)

    # -------------------------------------------------------------------------
    # Criteria J: Legacy single-fee receipt renders correctly
    # -------------------------------------------------------------------------

    def test_legacy_single_fee_receipt_renders(self):
        """Legacy single-fee receipt renders cleanly without regression."""
        receipt = Receipt.objects.create(
            student=self.student,
            amount=Decimal("120000.00"),
            paid_through="Cheque",
            term=self.term_1,
            payment_date=date(2028, 10, 1),
            payer="Mrs Musa",
            remarks="Full tuition payment",
        )
        FeePaymentAllocation.objects.create(
            receipt=receipt,
            fee_assignment=self.assignment_tuition_t1,
            amount=Decimal("120000.00"),
        )

        html = build_receipt_html(receipt)
        self.assertIn("Tuition", html)
        self.assertIn("First Term", html)
        self.assertIn("120,000.00", html)
        self.assertIn("Full tuition payment", html)

    # -------------------------------------------------------------------------
    # Criteria K: Unallocated receipt fallback does not crash
    # -------------------------------------------------------------------------

    def test_unallocated_receipt_fallback_does_not_crash(self):
        """Receipt with no allocations displays clean fallback notice and does not crash."""
        receipt = Receipt.objects.create(
            student=self.student,
            amount=Decimal("30000.00"),
            paid_through="Cash",
            term=None,
            payment_date=date(2028, 10, 5),
            payer="Ibrahim Musa",
        )

        html = build_receipt_html(receipt)
        self.assertIn("No fee allocation details available.", html)
        self.assertIn("30,000.00", html)
        # Must not derive a fake header term
        self.assertNotIn("Term: Current Term", html)
        self.assertNotIn("Term: None", html)
        self.assertNotIn("Term: Multiple / Mixed", html)

    # -------------------------------------------------------------------------
    # Criteria L: Missing optional metadata renders safely
    # -------------------------------------------------------------------------

    def test_missing_optional_metadata_renders_safely(self):
        """Receipt with all optional fields null/blank renders cleanly with dashes and no 'None' text."""
        receipt = Receipt.objects.create(
            student=None,
            amount=Decimal("10000.00"),
            paid_through="",
            term=None,
            payer="",
            reference_number=None,
            remarks=None,
            received_by=None,
        )
        # Also test with attributes explicitly set to None in memory
        receipt.payer = None
        receipt.payment_date = None

        html = build_receipt_html(receipt)
        self.assertNotIn("None", html)
        self.assertIn("10,000.00", html)
        self.assertIn("—", html)

    # -------------------------------------------------------------------------
    # Criteria M: Long fee description does not break HTML generation
    # -------------------------------------------------------------------------

    def test_long_fee_description_escaped_and_renders_cleanly(self):
        """Long fee names with special characters are safely escaped and formatted."""
        long_fee_name = "Special Development & Maintenance Infrastructure Levy <Approved Phase 2>"
        fee = FeeStructure.objects.create(
            name=long_fee_name,
            amount=Decimal("75000.00"),
            fee_type="Maintenance",
            recurrence=FeeRecurrence.ANNUAL,
            academic_year=self.year,
            term=None,
            created_by=self.user,
        )
        assignment = StudentFeeAssignment.objects.create(
            student=self.student,
            fee_structure=fee,
            academic_year=self.year,
            term=self.term_1,
            recurrence=FeeRecurrence.ANNUAL,
            amount_owed=Decimal("75000.00"),
            amount_paid=Decimal("0.00"),
        )
        receipt = Receipt.objects.create(
            student=self.student,
            amount=Decimal("75000.00"),
            paid_through="Bank Transfer",
            term=None,
        )
        FeePaymentAllocation.objects.create(
            receipt=receipt,
            fee_assignment=assignment,
            amount=Decimal("75000.00"),
        )

        html = build_receipt_html(receipt)
        # Check that HTML entities are escaped
        self.assertIn("Special Development &amp; Maintenance Infrastructure Levy &lt;Approved Phase 2&gt;", html)
        self.assertNotIn("<Approved Phase 2>", html)

    # -------------------------------------------------------------------------
    # Serializer Read Shape Enhancements
    # -------------------------------------------------------------------------

    def test_serializer_scope_label_and_header_term_display(self):
        """Serializers expose scope_label and header_term_display for frontend preview."""
        receipt = Receipt.objects.create(
            student=self.student,
            amount=Decimal("160000.00"),
            paid_through="Bank Transfer",
            term=None,
        )
        alloc_1 = FeePaymentAllocation.objects.create(
            receipt=receipt,
            fee_assignment=self.assignment_tuition_t1,
            amount=Decimal("120000.00"),
        )
        alloc_2 = FeePaymentAllocation.objects.create(
            receipt=receipt,
            fee_assignment=self.assignment_dev_levy,
            amount=Decimal("40000.00"),
        )

        alloc_ser = FeePaymentAllocationSerializer(alloc_1)
        self.assertEqual(alloc_ser.data["scope_label"], "First Term")

        alloc_ser_2 = FeePaymentAllocationSerializer(alloc_2)
        self.assertEqual(alloc_ser_2.data["scope_label"], "Annual")

        receipt_ser = ReceiptSerializer(receipt)
        self.assertEqual(receipt_ser.data["header_term_display"], "Multiple / Mixed")

    # -------------------------------------------------------------------------
    # API Download Endpoint
    # -------------------------------------------------------------------------

    def test_receipt_download_pdf_endpoint(self):
        """GET /api/finance/receipts/{id}/download/ returns 200 with application/pdf."""
        receipt = Receipt.objects.create(
            student=self.student,
            amount=Decimal("120000.00"),
            paid_through="Bank Transfer",
            term=self.term_1,
        )
        FeePaymentAllocation.objects.create(
            receipt=receipt,
            fee_assignment=self.assignment_tuition_t1,
            amount=Decimal("120000.00"),
        )

        url = f"/api/finance/receipts/{receipt.id}/download/"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(len(response.content) > 0)
        self.assertTrue(response.content.startswith(b"%PDF"))
