from datetime import date
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from school.testcases import TenantTestCase

from academic.models import ClassRoom, GradeLevel, Student, StudentClassEnrollment
from administration.models import AcademicYear, Term
from finance.models import (
    FeeApplicability,
    FeePaymentAllocation,
    FeeRecurrence,
    FeeStructure,
    Receipt,
    StudentFeeAssignment,
)


class CleanupFeeAssignmentsCommandTests(TenantTestCase):
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
            name="First Term 2026",
            academic_year=self.year_2026,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 15),
        )

        self.grade = GradeLevel.objects.update_or_create(
            system_code="CLN_G1",
            defaults={"section": "PRIMARY", "default_name": "Grade 1", "sequence_order": 1},
        )[0]
        self.classroom = ClassRoom.objects.create(
            name="Cleanup Room",
            grade_level=self.grade,
            capacity=30,
        )

        # 1. Returning student (enrolled in 2025/2026 and 2026/2027)
        self.student_ret = Student.objects.create(
            first_name="Returning",
            last_name="Student",
            admission_number="ADM-CLN-RET",
            is_active=True,
            classroom=self.classroom,
        )
        StudentClassEnrollment.objects.create(
            student=self.student_ret,
            classroom=self.classroom,
            academic_year=self.year_2025,
            is_active=False,
        )
        StudentClassEnrollment.objects.create(
            student=self.student_ret,
            classroom=self.classroom,
            academic_year=self.year_2026,
            is_active=True,
        )

        # 2. New student (enrolled only in 2026/2027)
        self.student_new = Student.objects.create(
            first_name="New",
            last_name="Student",
            admission_number="ADM-CLN-NEW",
            is_active=True,
            classroom=self.classroom,
        )
        StudentClassEnrollment.objects.create(
            student=self.student_new,
            classroom=self.classroom,
            academic_year=self.year_2026,
            is_active=True,
        )

    # =========================================================================
    # 1. Dry Run Test
    # =========================================================================
    def test_dry_run_identifies_inapplicable_and_deletes_nothing(self):
        """
        Dry-run finds inapplicable returning assignment, preserves applicable new student,
        and deletes nothing from the database.
        """
        fee = FeeStructure.objects.create(
            name="Admission Fee",
            logical_fee_key="admission-fee",
            amount=Decimal("50000.00"),
            recurrence=FeeRecurrence.ONE_TIME,
            applicability=FeeApplicability.NEW_STUDENTS_ONLY,
            academic_year=self.year_2026,
            is_mandatory=False,
        )

        assign_ret = StudentFeeAssignment.objects.create(
            student=self.student_ret,
            fee_structure=fee,
            term=self.term_2026_t1,
            amount_owed=Decimal("50000.00"),
            amount_paid=Decimal("0.00"),
            logical_fee_key="admission-fee",
            recurrence=FeeRecurrence.ONE_TIME,
            academic_year=self.year_2026,
        )
        assign_new = StudentFeeAssignment.objects.create(
            student=self.student_new,
            fee_structure=fee,
            term=self.term_2026_t1,
            amount_owed=Decimal("50000.00"),
            amount_paid=Decimal("0.00"),
            logical_fee_key="admission-fee",
            recurrence=FeeRecurrence.ONE_TIME,
            academic_year=self.year_2026,
        )

        out = StringIO()
        call_command(
            "cleanup_fee_assignments",
            schema=self.tenant.schema_name,
            fee_structure_id=fee.pk,
            dry_run=True,
            stdout=out,
        )
        output = out.getvalue()

        self.assertIn("Total assignments:      2", output)
        self.assertIn("Still applicable:       1", output)
        self.assertIn("Inapplicable:           1", output)
        self.assertIn("Safe to delete:         1", output)
        self.assertIn("No database changes were made (dry run).", output)

        # Verify nothing was deleted
        self.assertTrue(StudentFeeAssignment.objects.filter(pk=assign_ret.pk).exists())
        self.assertTrue(StudentFeeAssignment.objects.filter(pk=assign_new.pk).exists())

    # =========================================================================
    # 2. Live Run Test
    # =========================================================================
    def test_live_run_deletes_safe_inapplicable_and_preserves_applicable(self):
        """
        Live run deletes safe inapplicable assignment and preserves applicable assignment.
        """
        fee = FeeStructure.objects.create(
            name="Admission Fee",
            logical_fee_key="admission-fee",
            amount=Decimal("50000.00"),
            recurrence=FeeRecurrence.ONE_TIME,
            applicability=FeeApplicability.NEW_STUDENTS_ONLY,
            academic_year=self.year_2026,
            is_mandatory=False,
        )

        assign_ret = StudentFeeAssignment.objects.create(
            student=self.student_ret,
            fee_structure=fee,
            term=self.term_2026_t1,
            amount_owed=Decimal("50000.00"),
            amount_paid=Decimal("0.00"),
            logical_fee_key="admission-fee",
            recurrence=FeeRecurrence.ONE_TIME,
            academic_year=self.year_2026,
        )
        assign_new = StudentFeeAssignment.objects.create(
            student=self.student_new,
            fee_structure=fee,
            term=self.term_2026_t1,
            amount_owed=Decimal("50000.00"),
            amount_paid=Decimal("0.00"),
            logical_fee_key="admission-fee",
            recurrence=FeeRecurrence.ONE_TIME,
            academic_year=self.year_2026,
        )

        out = StringIO()
        call_command(
            "cleanup_fee_assignments",
            schema=self.tenant.schema_name,
            fee_structure_id=fee.pk,
            stdout=out,
        )
        output = out.getvalue()

        self.assertIn("Deleted: 1", output)
        self.assertIn("Preserved applicable: 1", output)
        self.assertIn("Successfully cleaned up 1 invalid fee assignment(s).", output)

        # Inapplicable returning student assignment deleted
        self.assertFalse(StudentFeeAssignment.objects.filter(pk=assign_ret.pk).exists())
        # Applicable new student assignment preserved
        self.assertTrue(StudentFeeAssignment.objects.filter(pk=assign_new.pk).exists())

    # =========================================================================
    # 3. Payment Safety Test
    # =========================================================================
    def test_payment_safety_blocks_deletion(self):
        """
        Inapplicable assignment with amount_paid > 0 is blocked from deletion.
        """
        fee = FeeStructure.objects.create(
            name="Admission Fee",
            logical_fee_key="admission-fee",
            amount=Decimal("50000.00"),
            recurrence=FeeRecurrence.ONE_TIME,
            applicability=FeeApplicability.NEW_STUDENTS_ONLY,
            academic_year=self.year_2026,
            is_mandatory=False,
        )

        assign_ret = StudentFeeAssignment.objects.create(
            student=self.student_ret,
            fee_structure=fee,
            term=self.term_2026_t1,
            amount_owed=Decimal("50000.00"),
            amount_paid=Decimal("20000.00"),  # Partial payment
            logical_fee_key="admission-fee",
            recurrence=FeeRecurrence.ONE_TIME,
            academic_year=self.year_2026,
        )

        out = StringIO()
        call_command(
            "cleanup_fee_assignments",
            schema=self.tenant.schema_name,
            fee_structure_id=fee.pk,
            stdout=out,
        )
        output = out.getvalue()

        self.assertIn("Blocked by payment:     1", output)
        self.assertIn("Deleted: 0", output)
        self.assertTrue(StudentFeeAssignment.objects.filter(pk=assign_ret.pk).exists())

    # =========================================================================
    # 4. Allocation Safety Test
    # =========================================================================
    def test_allocation_safety_blocks_deletion(self):
        """
        Inapplicable assignment with linked FeePaymentAllocation is blocked from deletion.
        """
        fee = FeeStructure.objects.create(
            name="Admission Fee",
            logical_fee_key="admission-fee",
            amount=Decimal("50000.00"),
            recurrence=FeeRecurrence.ONE_TIME,
            applicability=FeeApplicability.NEW_STUDENTS_ONLY,
            academic_year=self.year_2026,
            is_mandatory=False,
        )

        assign_ret = StudentFeeAssignment.objects.create(
            student=self.student_ret,
            fee_structure=fee,
            term=self.term_2026_t1,
            amount_owed=Decimal("50000.00"),
            amount_paid=Decimal("0.00"),
            logical_fee_key="admission-fee",
            recurrence=FeeRecurrence.ONE_TIME,
            academic_year=self.year_2026,
        )
        receipt = Receipt.objects.create(
            receipt_number=9901,
            student=self.student_ret,
            amount=Decimal("50000.00"),
            term=self.term_2026_t1,
        )
        FeePaymentAllocation.objects.create(
            receipt=receipt,
            fee_assignment=assign_ret,
            amount=Decimal("50000.00"),
        )

        out = StringIO()
        call_command(
            "cleanup_fee_assignments",
            schema=self.tenant.schema_name,
            fee_structure_id=fee.pk,
            stdout=out,
        )
        output = out.getvalue()

        self.assertIn("Deleted: 0", output)
        self.assertTrue(StudentFeeAssignment.objects.filter(pk=assign_ret.pk).exists())

    # =========================================================================
    # 5. Waiver Safety Test
    # =========================================================================
    def test_waiver_safety_blocks_deletion(self):
        """
        Inapplicable assignment marked is_waived is blocked from deletion.
        """
        fee = FeeStructure.objects.create(
            name="Admission Fee",
            logical_fee_key="admission-fee",
            amount=Decimal("50000.00"),
            recurrence=FeeRecurrence.ONE_TIME,
            applicability=FeeApplicability.NEW_STUDENTS_ONLY,
            academic_year=self.year_2026,
            is_mandatory=False,
        )

        assign_ret = StudentFeeAssignment.objects.create(
            student=self.student_ret,
            fee_structure=fee,
            term=self.term_2026_t1,
            amount_owed=Decimal("50000.00"),
            amount_paid=Decimal("0.00"),
            is_waived=True,
            waived_reason="Scholarship",
            logical_fee_key="admission-fee",
            recurrence=FeeRecurrence.ONE_TIME,
            academic_year=self.year_2026,
        )

        out = StringIO()
        call_command(
            "cleanup_fee_assignments",
            schema=self.tenant.schema_name,
            fee_structure_id=fee.pk,
            stdout=out,
        )
        output = out.getvalue()

        self.assertIn("Blocked by waiver:      1", output)
        self.assertIn("Deleted: 0", output)
        self.assertTrue(StudentFeeAssignment.objects.filter(pk=assign_ret.pk).exists())

    # =========================================================================
    # 6. Nonexistent Schema Test
    # =========================================================================
    def test_nonexistent_schema_raises_error(self):
        """
        Command fails safely with CommandError if an invalid schema is specified.
        """
        with self.assertRaises(CommandError) as ctx:
            call_command(
                "cleanup_fee_assignments",
                schema="invalid_schema_xyz",
                fee_structure_id=999,
            )
        self.assertIn("does not exist", str(ctx.exception))

    # =========================================================================
    # 7. Nonexistent FeeStructure ID Test
    # =========================================================================
    def test_nonexistent_fee_structure_raises_error(self):
        """
        Command fails safely with CommandError if FeeStructure is not found.
        """
        with self.assertRaises(CommandError) as ctx:
            call_command(
                "cleanup_fee_assignments",
                schema=self.tenant.schema_name,
                fee_structure_id=999999,
            )
        self.assertIn("does not exist", str(ctx.exception))

    # =========================================================================
    # 8. ALL_ELIGIBLE FeeStructure Test
    # =========================================================================
    def test_all_eligible_fee_structure_has_zero_cleanup_candidates(self):
        """
        If FeeStructure is ALL_ELIGIBLE, both new and returning students are applicable,
        so zero cleanup candidates are found.
        """
        fee = FeeStructure.objects.create(
            name="Tuition Fee",
            logical_fee_key="tuition-fee",
            amount=Decimal("70000.00"),
            recurrence=FeeRecurrence.PER_TERM,
            applicability=FeeApplicability.ALL_ELIGIBLE,
            academic_year=self.year_2026,
            term=self.term_2026_t1,
            is_mandatory=False,
        )

        assign_ret = StudentFeeAssignment.objects.create(
            student=self.student_ret,
            fee_structure=fee,
            term=self.term_2026_t1,
            amount_owed=Decimal("70000.00"),
            amount_paid=Decimal("0.00"),
            logical_fee_key="tuition-fee",
            recurrence=FeeRecurrence.PER_TERM,
            academic_year=self.year_2026,
        )
        assign_new = StudentFeeAssignment.objects.create(
            student=self.student_new,
            fee_structure=fee,
            term=self.term_2026_t1,
            amount_owed=Decimal("70000.00"),
            amount_paid=Decimal("0.00"),
            logical_fee_key="tuition-fee",
            recurrence=FeeRecurrence.PER_TERM,
            academic_year=self.year_2026,
        )

        out = StringIO()
        call_command(
            "cleanup_fee_assignments",
            schema=self.tenant.schema_name,
            fee_structure_id=fee.pk,
            stdout=out,
        )
        output = out.getvalue()

        self.assertIn("Total assignments:      2", output)
        self.assertIn("Still applicable:       2", output)
        self.assertIn("Inapplicable:           0", output)
        self.assertIn("Safe to delete:         0", output)
        self.assertTrue(StudentFeeAssignment.objects.filter(pk=assign_ret.pk).exists())
        self.assertTrue(StudentFeeAssignment.objects.filter(pk=assign_new.pk).exists())
