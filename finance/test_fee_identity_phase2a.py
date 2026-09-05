from datetime import date
from decimal import Decimal
import io

import importlib
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from school.testcases import TenantTestCase

from academic.models import ClassRoom, GradeLevel, Student, StudentClassEnrollment
from administration.models import AcademicYear, Term
from finance.models import (
    FeeApplicability,
    FeePaymentAllocation,
    FeeRecurrence,
    FeeStructure,
    FeeType,
    Payment,
    Receipt,
    StudentFeeAssignment,
)
from finance.services.fee_identity_audit_service import FeeIdentityAuditService

migration_0010 = importlib.import_module("finance.migrations.0010_fee_identity_backfill")
backfill_fee_identity = migration_0010.backfill_fee_identity

User = get_user_model()


class FeeIdentityPhase2ATests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        return super().setup_tenant(tenant)

    def setUp(self):
        super().setUp()
        self.year_2025 = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            active_year=False,
        )
        self.year_2026 = AcademicYear.objects.create(
            name="2026/2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 7, 31),
            active_year=True,
        )
        self.term_2026_t1 = Term.objects.create(
            name="First Term",
            academic_year=self.year_2026,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 15),
        )
        self.grade = GradeLevel.objects.update_or_create(
            system_code="PHASE2A_G1",
            defaults={"section": "PRIMARY", "default_name": "Grade 1", "sequence_order": 1},
        )[0]
        self.classroom = ClassRoom.objects.create(
            name="Phase 2A Class",
            grade_level=self.grade,
            capacity=30,
        )
        self.student = Student.objects.create(
            first_name="Ada",
            last_name="Lovelace",
            admission_number="ADM-P2A-001",
            parent_contact="08012345678",
            is_active=True,
        )
        self.accountant = User.objects.create_user(
            email="accountant-phase2a@test.local",
            password="password123",
            is_accountant=True,
        )

    def test_01_feestructure_backfill_and_no_semantic_inference(self):
        """
        Legacy FeeStructure with blank logical_fee_key receives slugify(name).
        Crucially, Admission Fee recurrence remains PER_TERM and ALL_ELIGIBLE (no policy inference).
        """
        fee = FeeStructure.objects.create(
            name="Admission Fee",
            amount=Decimal("50000.00"),
            academic_year=self.year_2026,
            term=self.term_2026_t1,
            fee_type=FeeType.ADMISSION,
            logical_fee_key="",
        )
        self.assertEqual(fee.logical_fee_key, "")
        self.assertEqual(fee.recurrence, FeeRecurrence.PER_TERM)
        self.assertEqual(fee.applicability, FeeApplicability.ALL_ELIGIBLE)

        backfill_fee_identity(apps, None)

        fee.refresh_from_db()
        self.assertEqual(fee.logical_fee_key, "admission-fee")
        # Ensure recurrence and applicability were NOT automatically modified
        self.assertEqual(fee.recurrence, FeeRecurrence.PER_TERM)
        self.assertEqual(fee.applicability, FeeApplicability.ALL_ELIGIBLE)

    def test_02_cross_year_identity_shares_same_logical_fee_key(self):
        """
        FeeStructures representing the same logical fee across different academic years
        share the same logical_fee_key without year/term/PK suffixes.
        """
        fee_y1 = FeeStructure.objects.create(
            name="Tuition Fee",
            amount=Decimal("100000.00"),
            academic_year=self.year_2025,
            logical_fee_key="",
        )
        fee_y2 = FeeStructure.objects.create(
            name="Tuition Fee",
            amount=Decimal("120000.00"),
            academic_year=self.year_2026,
            logical_fee_key="",
        )

        backfill_fee_identity(apps, None)

        fee_y1.refresh_from_db()
        fee_y2.refresh_from_db()
        self.assertEqual(fee_y1.logical_fee_key, "tuition-fee")
        self.assertEqual(fee_y2.logical_fee_key, "tuition-fee")
        self.assertNotEqual(fee_y1.pk, fee_y2.pk)

    def test_03_explicit_logical_key_is_preserved(self):
        """
        If a FeeStructure already has an explicit logical_fee_key, it must be preserved
        and NOT regenerated from the name.
        """
        fee = FeeStructure.objects.create(
            name="Registration / Application Fee",
            amount=Decimal("30000.00"),
            academic_year=self.year_2026,
            logical_fee_key="admission-fee",
        )

        backfill_fee_identity(apps, None)

        fee.refresh_from_db()
        self.assertEqual(fee.logical_fee_key, "admission-fee")

    def test_04_blank_or_unslugifiable_name_fallback(self):
        """
        If name produces an empty slug (e.g., symbols only), fallback is fee-{pk}.
        """
        fee = FeeStructure.objects.create(
            name="---",
            amount=Decimal("15000.00"),
            academic_year=self.year_2026,
            logical_fee_key="",
        )

        backfill_fee_identity(apps, None)

        fee.refresh_from_db()
        self.assertEqual(fee.logical_fee_key, f"fee-{fee.pk}")

    def test_05_assignment_snapshot_backfill(self):
        """
        Legacy StudentFeeAssignment with blank logical_fee_key and null academic_year
        receives snapshot metadata from its FeeStructure, but its recurrence remains unchanged.
        """
        fee = FeeStructure.objects.create(
            name="Laboratory Levy",
            amount=Decimal("20000.00"),
            academic_year=self.year_2026,
            term=self.term_2026_t1,
            recurrence=FeeRecurrence.ANNUAL,
            logical_fee_key="lab-levy",
        )
        assignment = StudentFeeAssignment.objects.create(
            student=self.student,
            fee_structure=fee,
            term=self.term_2026_t1,
            amount_owed=Decimal("20000.00"),
            logical_fee_key="",
            recurrence=FeeRecurrence.PER_TERM,  # default legacy
            academic_year=None,
        )

        backfill_fee_identity(apps, None)

        assignment.refresh_from_db()
        self.assertEqual(assignment.logical_fee_key, "lab-levy")
        self.assertEqual(assignment.academic_year, self.year_2026)
        # Crucially: recurrence must remain PER_TERM, never rewritten to FeeStructure's ANNUAL
        self.assertEqual(assignment.recurrence, FeeRecurrence.PER_TERM)

    def test_05b_feestructure_recurrence_change_does_not_rewrite_assignment_recurrence(self):
        """
        Changing a FeeStructure to ONE_TIME or ANNUAL before running the backfill
        does NOT rewrite an existing assignment's PER_TERM recurrence.
        """
        fee = FeeStructure.objects.create(
            name="Matriculation Fee",
            amount=Decimal("35000.00"),
            academic_year=self.year_2026,
            term=self.term_2026_t1,
            recurrence=FeeRecurrence.ONE_TIME,
            logical_fee_key="matriculation-fee",
        )
        assignment = StudentFeeAssignment.objects.create(
            student=self.student,
            fee_structure=fee,
            term=self.term_2026_t1,
            amount_owed=Decimal("35000.00"),
            logical_fee_key="",
            recurrence=FeeRecurrence.PER_TERM,
            academic_year=None,
        )

        backfill_fee_identity(apps, None)

        assignment.refresh_from_db()
        self.assertEqual(assignment.logical_fee_key, "matriculation-fee")
        self.assertEqual(assignment.academic_year, self.year_2026)
        # Assignment recurrence remains PER_TERM
        self.assertEqual(assignment.recurrence, FeeRecurrence.PER_TERM)

    def test_06_existing_assignment_metadata_preservation(self):
        """
        Existing assignment snapshot metadata (explicit key, explicit recurrence, explicit year)
        must NOT be overwritten by the backfill.
        """
        fee = FeeStructure.objects.create(
            name="Sports Fee",
            amount=Decimal("10000.00"),
            academic_year=self.year_2026,
            term=self.term_2026_t1,
            recurrence=FeeRecurrence.PER_TERM,
            logical_fee_key="sports-fee",
        )
        assignment = StudentFeeAssignment.objects.create(
            student=self.student,
            fee_structure=fee,
            term=self.term_2026_t1,
            amount_owed=Decimal("10000.00"),
            logical_fee_key="custom-sports-override",
            recurrence=FeeRecurrence.ONE_TIME,  # explicitly non-default
            academic_year=self.year_2025,  # explicitly set to older year
        )

        backfill_fee_identity(apps, None)

        assignment.refresh_from_db()
        self.assertEqual(assignment.logical_fee_key, "custom-sports-override")
        self.assertEqual(assignment.recurrence, FeeRecurrence.ONE_TIME)
        self.assertEqual(assignment.academic_year, self.year_2025)

    def test_07_financial_preservation(self):
        """
        Backfill must NOT alter financial totals, balances, waivers, or payment allocations.
        """
        fee = FeeStructure.objects.create(
            name="Term Tuition",
            amount=Decimal("80000.00"),
            academic_year=self.year_2026,
            term=self.term_2026_t1,
            logical_fee_key="",
        )
        assignment = StudentFeeAssignment.objects.create(
            student=self.student,
            fee_structure=fee,
            term=self.term_2026_t1,
            amount_owed=Decimal("80000.00"),
            amount_paid=Decimal("0.00"),
            is_waived=False,
            logical_fee_key="",
            academic_year=None,
        )
        receipt = Receipt.objects.create(
            student=self.student,
            amount=Decimal("30000.00"),
            term=self.term_2026_t1,
            received_by=self.accountant,
        )
        allocation = FeePaymentAllocation.objects.create(
            receipt=receipt,
            fee_assignment=assignment,
            amount=Decimal("30000.00"),
            allocated_by=self.accountant,
        )

        assignment.refresh_from_db()
        self.assertEqual(assignment.amount_paid, Decimal("30000.00"))
        self.assertEqual(assignment.balance, Decimal("50000.00"))

        original_assignment_id = assignment.id
        original_allocation_id = allocation.id
        original_amount_owed = assignment.amount_owed
        original_amount_paid = assignment.amount_paid
        original_balance = assignment.balance

        backfill_fee_identity(apps, None)

        assignment.refresh_from_db()
        self.assertEqual(assignment.id, original_assignment_id)
        self.assertEqual(assignment.amount_owed, original_amount_owed)
        self.assertEqual(assignment.amount_paid, original_amount_paid)
        self.assertEqual(assignment.balance, original_balance)
        self.assertFalse(assignment.is_waived)
        self.assertEqual(assignment.logical_fee_key, "term-tuition")
        self.assertEqual(assignment.academic_year, self.year_2026)

        # Payment allocations remain untouched
        self.assertEqual(assignment.payment_allocations.count(), 1)
        self.assertEqual(assignment.payment_allocations.first().id, original_allocation_id)
        self.assertEqual(assignment.payment_allocations.first().amount, Decimal("30000.00"))

    def test_08_backfill_idempotency(self):
        """
        Running the backfill multiple times is safe and deterministic.
        """
        fee = FeeStructure.objects.create(
            name="ICT Fee",
            amount=Decimal("15000.00"),
            academic_year=self.year_2026,
            logical_fee_key="",
        )
        assignment = StudentFeeAssignment.objects.create(
            student=self.student,
            fee_structure=fee,
            term=self.term_2026_t1,
            amount_owed=Decimal("15000.00"),
            logical_fee_key="",
            academic_year=None,
        )

        # First run
        backfill_fee_identity(apps, None)
        fee.refresh_from_db()
        assignment.refresh_from_db()
        self.assertEqual(fee.logical_fee_key, "ict-fee")
        self.assertEqual(assignment.logical_fee_key, "ict-fee")

        # Second run
        backfill_fee_identity(apps, None)
        fee.refresh_from_db()
        assignment.refresh_from_db()
        self.assertEqual(fee.logical_fee_key, "ict-fee")
        self.assertEqual(assignment.logical_fee_key, "ict-fee")

    def test_09_audit_command_and_service(self):
        """
        Audit service and command detect cross-year keys, same-year collisions,
        and report cleanly without mutating records.
        """
        # Cross-year key: 'tuition-fee' in 2025 and 2026
        FeeStructure.objects.create(
            name="Tuition Fee",
            amount=Decimal("50000.00"),
            academic_year=self.year_2025,
            logical_fee_key="tuition-fee",
        )
        FeeStructure.objects.create(
            name="Tuition Fee",
            amount=Decimal("60000.00"),
            academic_year=self.year_2026,
            logical_fee_key="tuition-fee",
        )

        # Same-year duplicate: 'uniform-fee' twice in 2026
        FeeStructure.objects.create(
            name="Uniform Fee Primary",
            amount=Decimal("20000.00"),
            academic_year=self.year_2026,
            logical_fee_key="uniform-fee",
        )
        FeeStructure.objects.create(
            name="Uniform Fee Secondary",
            amount=Decimal("25000.00"),
            academic_year=self.year_2026,
            logical_fee_key="uniform-fee",
        )

        # Blank key FeeStructure
        FeeStructure.objects.create(
            name="Un-keyed Fee",
            amount=Decimal("5000.00"),
            academic_year=self.year_2026,
            logical_fee_key="",
        )

        audit_result = FeeIdentityAuditService.audit()
        fs_audit = audit_result["fee_structures"]

        self.assertGreaterEqual(fs_audit["total"], 5)
        self.assertGreaterEqual(fs_audit["blank_keys"], 1)
        self.assertGreaterEqual(fs_audit["cross_year_keys_count"], 1)
        self.assertGreaterEqual(fs_audit["same_year_duplicate_keys_count"], 1)

        # Verify management command execution
        out = io.StringIO()
        call_command("audit_fee_identity", stdout=out)
        output = out.getvalue()

        self.assertIn("FEE IDENTITY & RECURRENCE SNAPSHOT AUDIT REPORT", output)
        self.assertIn("tuition-fee", output)
        self.assertIn("CROSS-YEAR", output)
        self.assertIn("uniform-fee", output)
        self.assertIn("SAME-YEAR-DUPLICATE", output)
        self.assertIn("Audit complete (read-only; no database records were modified)", output)
