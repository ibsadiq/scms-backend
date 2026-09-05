from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from school.testcases import TenantTestCase

from academic.models import ClassRoom, GradeLevel, Student, StudentClassEnrollment
from administration.models import AcademicYear, Term
from finance.models import (
    FeeRecurrence,
    FeeStructure,
    FeeTermSchedule,
    StudentFeeAssignment,
)
from finance.services import FeeAssignmentService


class FeeRecurrencePhase3ATests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        return super().setup_tenant(tenant)

    def setUp(self):
        super().setUp()
        self.year_2026 = AcademicYear.objects.create(
            name="2026/2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 7, 31),
            active_year=True,
        )
        self.year_2027 = AcademicYear.objects.create(
            name="2027/2028",
            start_date=date(2027, 9, 1),
            end_date=date(2028, 7, 31),
            active_year=False,
        )
        self.term_2026_t1 = Term.objects.create(
            name="First Term 2026",
            academic_year=self.year_2026,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 15),
        )
        self.term_2026_t2 = Term.objects.create(
            name="Second Term 2026",
            academic_year=self.year_2026,
            start_date=date(2027, 1, 10),
            end_date=date(2027, 4, 10),
        )
        self.term_2026_t3 = Term.objects.create(
            name="Third Term 2026",
            academic_year=self.year_2026,
            start_date=date(2027, 4, 25),
            end_date=date(2027, 7, 20),
        )
        self.term_2027_t1 = Term.objects.create(
            name="First Term 2027",
            academic_year=self.year_2027,
            start_date=date(2027, 9, 1),
            end_date=date(2027, 12, 15),
        )
        self.grade = GradeLevel.objects.update_or_create(
            system_code="PHASE3A_G1",
            defaults={"section": "PRIMARY", "default_name": "Grade 1", "sequence_order": 1},
        )[0]
        self.classroom = ClassRoom.objects.create(
            name="Phase 3A Room",
            grade_level=self.grade,
            capacity=30,
        )
        self.student_a = Student.objects.create(
            first_name="Ada",
            last_name="Lovelace",
            admission_number="ADM-P3A-001",
            parent_contact="08011111111",
            is_active=True,
        )
        self.student_b = Student.objects.create(
            first_name="Charles",
            last_name="Babbage",
            admission_number="ADM-P3A-002",
            parent_contact="08022222222",
            is_active=True,
        )
        self.enrollment_a = StudentClassEnrollment.objects.create(
            student=self.student_a,
            classroom=self.classroom,
            academic_year=self.year_2026,
            is_active=True,
        )
        self.enrollment_b = StudentClassEnrollment.objects.create(
            student=self.student_b,
            classroom=self.classroom,
            academic_year=self.year_2026,
            is_active=True,
        )

    # =========================================================================
    # 1. PER_TERM Tests
    # =========================================================================

    def test_per_term_term_none_creates_per_term_obligation(self):
        """
        PER_TERM fee with term=None represents an obligation for every term
        in the academic year. Syncing Term 1 creates Term 1 obligation, repeated
        sync is idempotent, and syncing Term 2 creates Term 2 obligation.
        """
        fee = FeeStructure.objects.create(
            name="Tuition Fee",
            amount=Decimal("40000.00"),
            academic_year=self.year_2026,
            term=None,
            logical_fee_key="tuition-fee",
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=True,
        )
        FeeTermSchedule.objects.create(
            fee_structure=fee,
            term=self.term_2026_t1,
            due_date=self.term_2026_t1.start_date,
        )
        FeeTermSchedule.objects.create(
            fee_structure=fee,
            term=self.term_2026_t2,
            due_date=self.term_2026_t2.start_date,
        )
        FeeTermSchedule.objects.create(
            fee_structure=fee,
            term=self.term_2026_t3,
            due_date=self.term_2026_t3.start_date,
        )

        # 1. Sync for Term 1
        res1 = FeeAssignmentService.sync_fees_for_enrollment(
            enrollment=self.enrollment_a,
            term=self.term_2026_t1,
            return_details=True,
        )
        self.assertEqual(res1["created_count"], 1)
        self.assertEqual(res1["existing_count"], 0)

        assign_t1 = StudentFeeAssignment.objects.get(
            student=self.student_a, logical_fee_key="tuition-fee", term=self.term_2026_t1
        )
        self.assertEqual(assign_t1.amount_owed, Decimal("40000.00"))

        # 2. Repeated sync for Term 1 is strictly idempotent
        res1_repeat = FeeAssignmentService.sync_fees_for_enrollment(
            enrollment=self.enrollment_a,
            term=self.term_2026_t1,
            return_details=True,
        )
        self.assertEqual(res1_repeat["created_count"], 0)
        self.assertEqual(res1_repeat["existing_count"], 1)

        # 3. Sync for Term 2 creates new Term 2 obligation
        res2 = FeeAssignmentService.sync_fees_for_enrollment(
            enrollment=self.enrollment_a,
            term=self.term_2026_t2,
            return_details=True,
        )
        self.assertEqual(res2["created_count"], 1)
        self.assertEqual(res2["existing_count"], 0)

        self.assertEqual(
            StudentFeeAssignment.objects.filter(
                student=self.student_a, logical_fee_key="tuition-fee"
            ).count(),
            2,
        )

    def test_per_term_specific_term_only_assigned_in_that_term(self):
        """
        PER_TERM fee with a specific term is assigned only when processing that term.
        """
        fee_t1 = FeeStructure.objects.create(
            name="First Term Science Practical",
            amount=Decimal("12000.00"),
            academic_year=self.year_2026,
            term=self.term_2026_t1,
            logical_fee_key="science-practical",
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=True,
        )

        # Processing Term 2 must not create the Term 1 fee
        res_t2 = FeeAssignmentService.sync_fees_for_enrollment(
            enrollment=self.enrollment_a,
            term=self.term_2026_t2,
            return_details=True,
        )
        self.assertEqual(res_t2["created_count"], 0)
        self.assertFalse(
            StudentFeeAssignment.objects.filter(
                student=self.student_a, fee_structure=fee_t1
            ).exists()
        )

        # Processing Term 1 creates the fee
        res_t1 = FeeAssignmentService.sync_fees_for_enrollment(
            enrollment=self.enrollment_a,
            term=self.term_2026_t1,
            return_details=True,
        )
        self.assertEqual(res_t1["created_count"], 1)
        self.assertTrue(
            StudentFeeAssignment.objects.filter(
                student=self.student_a, fee_structure=fee_t1, term=self.term_2026_t1
            ).exists()
        )

    def test_per_term_snapshots_metadata(self):
        """
        New assignments snapshot logical_fee_key, recurrence, and academic_year.
        """
        fee = FeeStructure.objects.create(
            name="Term Activity",
            amount=Decimal("5000.00"),
            academic_year=self.year_2026,
            term=self.term_2026_t1,
            logical_fee_key="term-activity",
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=True,
        )
        created = FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee,
            student=self.student_a,
            term=self.term_2026_t1,
        )
        self.assertEqual(created, 1)

        assignment = StudentFeeAssignment.objects.get(
            student=self.student_a, fee_structure=fee
        )
        self.assertEqual(assignment.logical_fee_key, "term-activity")
        self.assertEqual(assignment.recurrence, FeeRecurrence.PER_TERM)
        self.assertEqual(assignment.academic_year, self.year_2026)

    # =========================================================================
    # 2. ANNUAL Tests
    # =========================================================================

    def test_annual_term_none_created_once_per_academic_year(self):
        """
        ANNUAL fee with term=None is created in the first processed term.
        Subsequent terms in that academic year reuse/skip the existing obligation.
        """
        fee = FeeStructure.objects.create(
            name="Annual PTA Levy",
            amount=Decimal("15000.00"),
            academic_year=self.year_2026,
            term=None,
            logical_fee_key="annual-pta-levy",
            recurrence=FeeRecurrence.ANNUAL,
            is_mandatory=True,
        )

        # Term 1 creates obligation
        res_t1 = FeeAssignmentService.sync_fees_for_enrollment(
            enrollment=self.enrollment_a,
            term=self.term_2026_t1,
            return_details=True,
        )
        self.assertEqual(res_t1["created_count"], 1)
        self.assertEqual(res_t1["existing_count"], 0)

        # Term 2 reuses/skips existing obligation
        res_t2 = FeeAssignmentService.sync_fees_for_enrollment(
            enrollment=self.enrollment_a,
            term=self.term_2026_t2,
            return_details=True,
        )
        self.assertEqual(res_t2["created_count"], 0)
        self.assertEqual(res_t2["existing_count"], 1)

        # Term 3 reuses/skips existing obligation
        res_t3 = FeeAssignmentService.sync_fees_for_enrollment(
            enrollment=self.enrollment_a,
            term=self.term_2026_t3,
            return_details=True,
        )
        self.assertEqual(res_t3["created_count"], 0)
        self.assertEqual(res_t3["existing_count"], 1)

        # Exactly 1 assignment exists across the whole academic year
        self.assertEqual(
            StudentFeeAssignment.objects.filter(
                student=self.student_a, logical_fee_key="annual-pta-levy"
            ).count(),
            1,
        )

    def test_annual_mid_session_enrollment_targets_entry_term(self):
        """
        When a student enrolls mid-session (e.g. Term 2), an ANNUAL term=None
        fee targets their entry term (Term 2) rather than forcing First Term.
        """
        fee = FeeStructure.objects.create(
            name="Development Levy",
            amount=Decimal("30000.00"),
            academic_year=self.year_2026,
            term=None,
            logical_fee_key="dev-levy",
            recurrence=FeeRecurrence.ANNUAL,
            is_mandatory=True,
        )

        # Student B is synced for the first time during Term 2
        res = FeeAssignmentService.sync_fees_for_enrollment(
            enrollment=self.enrollment_b,
            term=self.term_2026_t2,
            return_details=True,
        )
        self.assertEqual(res["created_count"], 1)

        assignment = StudentFeeAssignment.objects.get(
            student=self.student_b, logical_fee_key="dev-levy"
        )
        self.assertEqual(assignment.term, self.term_2026_t2)
        self.assertEqual(assignment.academic_year, self.year_2026)

    def test_annual_allowed_in_different_academic_year(self):
        """
        Same student and same logical_fee_key can receive a new ANNUAL obligation
        in a subsequent academic year.
        """
        fee_2026 = FeeStructure.objects.create(
            name="Annual Sports Levy 2026",
            amount=Decimal("10000.00"),
            academic_year=self.year_2026,
            term=None,
            logical_fee_key="annual-sports-levy",
            recurrence=FeeRecurrence.ANNUAL,
            is_mandatory=True,
        )
        fee_2027 = FeeStructure.objects.create(
            name="Annual Sports Levy 2027",
            amount=Decimal("12000.00"),
            academic_year=self.year_2027,
            term=None,
            logical_fee_key="annual-sports-levy",
            recurrence=FeeRecurrence.ANNUAL,
            is_mandatory=True,
        )

        # Year 2026 assignment
        created_2026 = FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee_2026,
            student=self.student_a,
            term=self.term_2026_t1,
        )
        self.assertEqual(created_2026, 1)

        # Year 2027 assignment (new year)
        created_2027 = FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee_2027,
            student=self.student_a,
            term=self.term_2027_t1,
        )
        self.assertEqual(created_2027, 1)

        assignments = StudentFeeAssignment.objects.filter(
            student=self.student_a, logical_fee_key="annual-sports-levy"
        ).order_by("academic_year__start_date")
        self.assertEqual(assignments.count(), 2)
        self.assertEqual(assignments[0].academic_year, self.year_2026)
        self.assertEqual(assignments[1].academic_year, self.year_2027)

    def test_annual_replacement_structure_produces_no_duplicate(self):
        """
        Two FeeStructure rows in the same academic year sharing the same logical_fee_key
        must produce only one ANNUAL obligation for a student.
        """
        fee_row_1 = FeeStructure.objects.create(
            name="Library Maintenance Old",
            amount=Decimal("8000.00"),
            academic_year=self.year_2026,
            term=self.term_2026_t1,
            logical_fee_key="library-maintenance",
            recurrence=FeeRecurrence.ANNUAL,
            is_mandatory=False,
        )
        fee_row_2 = FeeStructure.objects.create(
            name="Library Maintenance New",
            amount=Decimal("8000.00"),
            academic_year=self.year_2026,
            term=self.term_2026_t2,
            logical_fee_key="library-maintenance",
            recurrence=FeeRecurrence.ANNUAL,
            is_mandatory=False,
        )

        # First structure assigns
        created_1 = FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee_row_1,
            student=self.student_a,
            term=self.term_2026_t1,
        )
        self.assertEqual(created_1, 1)

        # Replacement structure skips assignment because logical obligation already exists
        created_2 = FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee_row_2,
            student=self.student_a,
            term=self.term_2026_t2,
        )
        self.assertEqual(created_2, 0)

        self.assertEqual(
            StudentFeeAssignment.objects.filter(
                student=self.student_a, logical_fee_key="library-maintenance"
            ).count(),
            1,
        )

    # =========================================================================
    # 3. ONE_TIME Tests
    # =========================================================================

    def test_onetime_repeated_sync_creates_single_lifetime_obligation(self):
        """
        ONE_TIME fee creates exactly 1 obligation across repeated sync operations.
        """
        fee = FeeStructure.objects.create(
            name="Lifetime Registration",
            amount=Decimal("25000.00"),
            academic_year=self.year_2026,
            term=None,
            logical_fee_key="lifetime-reg",
            recurrence=FeeRecurrence.ONE_TIME,
            is_mandatory=True,
        )
        # Sync 1
        res1 = FeeAssignmentService.sync_fees_for_enrollment(
            enrollment=self.enrollment_a,
            term=self.term_2026_t1,
            return_details=True,
        )
        self.assertEqual(res1["created_count"], 1)

        # Sync 2
        res2 = FeeAssignmentService.sync_fees_for_enrollment(
            enrollment=self.enrollment_a,
            term=self.term_2026_t1,
            return_details=True,
        )
        self.assertEqual(res2["created_count"], 0)
        self.assertEqual(res2["existing_count"], 1)

        self.assertEqual(
            StudentFeeAssignment.objects.filter(
                student=self.student_a, logical_fee_key="lifetime-reg"
            ).count(),
            1,
        )

    def test_onetime_subsequent_terms_create_no_duplicates(self):
        """
        ONE_TIME fee assigned in Term 1 is not duplicated when syncing Term 2 or Term 3.
        """
        fee = FeeStructure.objects.create(
            name="Admission Fee",
            amount=Decimal("35000.00"),
            academic_year=self.year_2026,
            term=None,
            logical_fee_key="admission-fee",
            recurrence=FeeRecurrence.ONE_TIME,
            is_mandatory=True,
        )
        FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee,
            student=self.student_a,
            term=self.term_2026_t1,
        )

        # Term 2 sync
        res_t2 = FeeAssignmentService.sync_fees_for_enrollment(
            enrollment=self.enrollment_a,
            term=self.term_2026_t2,
            return_details=True,
        )
        self.assertEqual(res_t2["created_count"], 0)
        self.assertEqual(res_t2["existing_count"], 1)

        # Term 3 sync
        res_t3 = FeeAssignmentService.sync_fees_for_enrollment(
            enrollment=self.enrollment_a,
            term=self.term_2026_t3,
            return_details=True,
        )
        self.assertEqual(res_t3["created_count"], 0)
        self.assertEqual(res_t3["existing_count"], 1)

    def test_onetime_subsequent_academic_year_creates_no_duplicates(self):
        """
        ONE_TIME obligation spans the student's lifetime: creating a new FeeStructure
        in a subsequent academic year must NOT assign another obligation to the student.
        """
        fee_2026 = FeeStructure.objects.create(
            name="Admission Fee 2026",
            amount=Decimal("35000.00"),
            academic_year=self.year_2026,
            term=None,
            logical_fee_key="admission-fee",
            recurrence=FeeRecurrence.ONE_TIME,
            is_mandatory=False,
        )
        fee_2027 = FeeStructure.objects.create(
            name="Admission Fee 2027",
            amount=Decimal("40000.00"),
            academic_year=self.year_2027,
            term=None,
            logical_fee_key="admission-fee",
            recurrence=FeeRecurrence.ONE_TIME,
            is_mandatory=False,
        )

        # Assigned in 2026
        FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee_2026,
            student=self.student_a,
            term=self.term_2026_t1,
        )

        # Attempting assignment in 2027 under new FeeStructure row
        created_2027 = FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee_2027,
            student=self.student_a,
            term=self.term_2027_t1,
        )
        self.assertEqual(created_2027, 0)

        # Student still has exactly 1 lifetime assignment
        self.assertEqual(
            StudentFeeAssignment.objects.filter(
                student=self.student_a, logical_fee_key="admission-fee"
            ).count(),
            1,
        )

    def test_onetime_different_students_both_receive_obligation(self):
        """
        ONE_TIME uniqueness is per-student; different students each receive their obligation.
        """
        fee = FeeStructure.objects.create(
            name="Alumni Endowment",
            amount=Decimal("20000.00"),
            academic_year=self.year_2026,
            term=None,
            logical_fee_key="alumni-endowment",
            recurrence=FeeRecurrence.ONE_TIME,
            is_mandatory=True,
        )
        c_a = FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee, student=self.student_a, term=self.term_2026_t1
        )
        c_b = FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee, student=self.student_b, term=self.term_2026_t1
        )
        self.assertEqual(c_a, 1)
        self.assertEqual(c_b, 1)
        self.assertEqual(
            StudentFeeAssignment.objects.filter(logical_fee_key="alumni-endowment").count(),
            2,
        )

    # =========================================================================
    # 4. Blank Logical Key Validation
    # =========================================================================

    def test_blank_key_validation_fails_for_annual_and_onetime(self):
        """
        ANNUAL or ONE_TIME FeeStructures missing logical_fee_key fail safely
        with ValidationError to prevent unindexed / corrupt recurrence state.
        """
        fee_onetime = FeeStructure.objects.create(
            name="Invalid One Time",
            amount=Decimal("10000.00"),
            academic_year=self.year_2026,
            logical_fee_key="",
            recurrence=FeeRecurrence.ONE_TIME,
            is_mandatory=False,
        )
        with self.assertRaises(ValidationError) as ctx:
            FeeAssignmentService.assign_fee_to_student(
                fee_structure=fee_onetime,
                student=self.student_a,
                term=self.term_2026_t1,
            )
        self.assertIn("logical_fee_key is blank", str(ctx.exception))

        fee_annual = FeeStructure.objects.create(
            name="Invalid Annual",
            amount=Decimal("10000.00"),
            academic_year=self.year_2026,
            logical_fee_key="   ",
            recurrence=FeeRecurrence.ANNUAL,
            is_mandatory=False,
        )
        with self.assertRaises(ValidationError) as ctx2:
            FeeAssignmentService.assign_fee_to_student(
                fee_structure=fee_annual,
                student=self.student_a,
                term=self.term_2026_t1,
            )
        self.assertIn("logical_fee_key is blank", str(ctx2.exception))

    def test_blank_key_succeeds_for_legacy_per_term(self):
        """
        Legacy PER_TERM FeeStructures are permitted to have a blank logical_fee_key
        to preserve full backward compatibility with un-migrated or legacy fixtures.
        """
        fee_per_term = FeeStructure.objects.create(
            name="Legacy Per Term Fee",
            amount=Decimal("10000.00"),
            academic_year=self.year_2026,
            term=self.term_2026_t1,
            logical_fee_key="",
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=False,
        )
        created = FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee_per_term,
            student=self.student_a,
            term=self.term_2026_t1,
        )
        self.assertEqual(created, 1)

        assignment = StudentFeeAssignment.objects.get(
            student=self.student_a, fee_structure=fee_per_term
        )
        self.assertEqual(assignment.logical_fee_key, "")
        self.assertEqual(assignment.recurrence, FeeRecurrence.PER_TERM)

    # =========================================================================
    # 5. Preservation of Financial State
    # =========================================================================

    def test_existing_financial_state_and_waivers_preserved(self):
        """
        Synchronization must never overwrite existing amounts, payments, or waivers.
        """
        fee = FeeStructure.objects.create(
            name="Tuition Fee",
            amount=Decimal("50000.00"),
            academic_year=self.year_2026,
            term=self.term_2026_t1,
            logical_fee_key="tuition-preservation",
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=True,
        )
        # Create pre-existing assignment with payments and waiver
        existing = StudentFeeAssignment.objects.create(
            student=self.student_a,
            fee_structure=fee,
            term=self.term_2026_t1,
            amount_owed=Decimal("50000.00"),
            amount_paid=Decimal("20000.00"),
            is_waived=True,
            waived_reason="Merit Scholarship",
            logical_fee_key="tuition-preservation",
            recurrence=FeeRecurrence.PER_TERM,
            academic_year=self.year_2026,
        )

        # Run enrollment sync
        res = FeeAssignmentService.sync_fees_for_enrollment(
            enrollment=self.enrollment_a,
            term=self.term_2026_t1,
            return_details=True,
        )
        self.assertEqual(res["created_count"], 0)
        self.assertEqual(res["existing_count"], 1)

        # Reload and verify financial state remains unchanged
        existing.refresh_from_db()
        self.assertEqual(existing.amount_owed, Decimal("50000.00"))
        self.assertEqual(existing.amount_paid, Decimal("20000.00"))
        self.assertTrue(existing.is_waived)
        self.assertEqual(existing.waived_reason, "Merit Scholarship")

    # =========================================================================
    # 6. Concurrency & Race Handling
    # =========================================================================

    def test_concurrency_race_returns_competing_assignment(self):
        """
        When a concurrent worker wins the race and inserts the assignment,
        _create_assignment_with_snapshot catches IntegrityError, retrieves
        the newly created assignment, and returns (existing, False).
        """
        fee = FeeStructure.objects.create(
            name="Race Test Fee",
            amount=Decimal("10000.00"),
            academic_year=self.year_2026,
            term=self.term_2026_t1,
            logical_fee_key="race-test-fee",
            recurrence=FeeRecurrence.ONE_TIME,
            is_mandatory=False,
        )

        # Pre-create the assignment simulating competing transaction winner
        winner_assignment = StudentFeeAssignment.objects.create(
            student=self.student_a,
            fee_structure=fee,
            term=self.term_2026_t1,
            amount_owed=Decimal("10000.00"),
            amount_paid=Decimal("0.00"),
            logical_fee_key="race-test-fee",
            recurrence=FeeRecurrence.ONE_TIME,
            academic_year=self.year_2026,
        )

        # Mock objects.create to simulate IntegrityError raised by database
        with patch.object(
            StudentFeeAssignment.objects,
            "create",
            side_effect=IntegrityError("duplicate key violates unique constraint"),
        ):
            assignment, created = FeeAssignmentService._create_assignment_with_snapshot(
                student=self.student_a,
                fee_structure=fee,
                target_term=self.term_2026_t1,
            )

        self.assertFalse(created)
        self.assertEqual(assignment.pk, winner_assignment.pk)

    def test_unrelated_integrity_error_is_reraised(self):
        """
        If an IntegrityError occurs that cannot be attributed to a competing
        recurrence assignment (i.e. no matching obligation exists), it must be re-raised.
        """
        fee = FeeStructure.objects.create(
            name="Unrelated Error Fee",
            amount=Decimal("10000.00"),
            academic_year=self.year_2026,
            term=self.term_2026_t1,
            logical_fee_key="unrelated-fee",
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=False,
        )

        with patch.object(
            StudentFeeAssignment.objects,
            "create",
            side_effect=IntegrityError("unrelated foreign key violation"),
        ):
            with self.assertRaises(IntegrityError):
                FeeAssignmentService._create_assignment_with_snapshot(
                    student=self.student_a,
                    fee_structure=fee,
                    target_term=self.term_2026_t1,
                )

    # =========================================================================
    # 7. Signal Integration
    # =========================================================================

    def test_fee_structure_post_save_does_not_duplicate_annual_or_onetime(self):
        """
        Creating a new FeeStructure with is_mandatory=True triggers post_save,
        which must respect recurrence rules and not duplicate existing obligations.
        """
        # Pre-assign student_a for ONE_TIME fee
        fee_old = FeeStructure.objects.create(
            name="Initial Admission",
            amount=Decimal("20000.00"),
            academic_year=self.year_2026,
            term=self.term_2026_t1,
            logical_fee_key="signal-admission-key",
            recurrence=FeeRecurrence.ONE_TIME,
            is_mandatory=False,
        )
        StudentFeeAssignment.objects.create(
            student=self.student_a,
            fee_structure=fee_old,
            term=self.term_2026_t1,
            amount_owed=Decimal("20000.00"),
            logical_fee_key="signal-admission-key",
            recurrence=FeeRecurrence.ONE_TIME,
            academic_year=self.year_2026,
        )

        # Directly invoke assign_fee (simulating post_save signal execution)
        fee_new = FeeStructure.objects.create(
            name="New Admission Row",
            amount=Decimal("25000.00"),
            academic_year=self.year_2026,
            term=self.term_2026_t2,
            logical_fee_key="signal-admission-key",
            recurrence=FeeRecurrence.ONE_TIME,
            is_mandatory=True,
        )
        assigned_count = FeeAssignmentService.assign_fee(fee_structure=fee_new)

        # Student A is skipped; Student B receives the fee
        self.assertEqual(assigned_count, 1)
        self.assertEqual(
            StudentFeeAssignment.objects.filter(
                student=self.student_a, logical_fee_key="signal-admission-key"
            ).count(),
            1,
        )
        self.assertEqual(
            StudentFeeAssignment.objects.filter(
                student=self.student_b, logical_fee_key="signal-admission-key"
            ).count(),
            1,
        )

    def test_term_post_save_does_not_duplicate_annual_or_onetime(self):
        """
        When a new Term is created and scheduled fees are processed:
        - PER_TERM fees with term=None create obligations for the new term.
        - ANNUAL fees already assigned in earlier terms are skipped.
        - ONE_TIME fees are not duplicated.
        """
        # 1. PER_TERM fee (term=None)
        fee_signal = FeeStructure.objects.create(
            name="Tuition Signal",
            amount=Decimal("30000.00"),
            academic_year=self.year_2026,
            term=None,
            logical_fee_key="tuition-signal",
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=True,
        )
        # 2. ANNUAL fee (term=None)
        annual_fee = FeeStructure.objects.create(
            name="Annual Signal",
            amount=Decimal("15000.00"),
            academic_year=self.year_2026,
            term=None,
            logical_fee_key="annual-signal",
            recurrence=FeeRecurrence.ANNUAL,
            is_mandatory=True,
        )
        # Pre-assign ANNUAL fee to student_a in Term 1
        StudentFeeAssignment.objects.create(
            student=self.student_a,
            fee_structure=annual_fee,
            term=self.term_2026_t1,
            amount_owed=Decimal("15000.00"),
            logical_fee_key="annual-signal",
            recurrence=FeeRecurrence.ANNUAL,
            academic_year=self.year_2026,
        )

        # Create a new Term 4
        new_term = Term.objects.create(
            name="Fourth Term Signal",
            academic_year=self.year_2026,
            start_date=date(2027, 8, 1),
            end_date=date(2027, 8, 30),
        )
        FeeTermSchedule.objects.create(
            fee_structure=fee_signal,
            term=new_term,
            due_date=new_term.start_date,
        )

        # Manually run the term fee assignment handler on new_term
        # (mirroring schedule_fees_for_term logic)
        fee_ids = list(
            FeeStructure.objects.filter(
                academic_year=new_term.academic_year,
                is_mandatory=True,
            ).filter(term=new_term).values_list("pk", flat=True)
        ) + list(
            FeeStructure.objects.filter(
                academic_year=new_term.academic_year,
                is_mandatory=True,
                term__isnull=True,
            ).exclude(recurrence=FeeRecurrence.ONE_TIME).values_list("pk", flat=True)
        )

        for fee_id in fee_ids:
            fee_obj = FeeStructure.objects.get(pk=fee_id)
            FeeAssignmentService.assign_fee(fee_structure=fee_obj, term=new_term)

        # Student A still has only 1 ANNUAL assignment for annual-signal
        self.assertEqual(
            StudentFeeAssignment.objects.filter(
                student=self.student_a, logical_fee_key="annual-signal"
            ).count(),
            1,
        )
        # Student A received the PER_TERM tuition for new_term
        self.assertTrue(
            StudentFeeAssignment.objects.filter(
                student=self.student_a, logical_fee_key="tuition-signal", term=new_term
            ).exists()
        )
