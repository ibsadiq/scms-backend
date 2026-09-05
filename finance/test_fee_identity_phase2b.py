from datetime import date
from decimal import Decimal
import importlib

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db import connection, IntegrityError, transaction
from school.testcases import TenantTestCase, TenantTransactionTestCase

from academic.models import ClassRoom, GradeLevel, Student
from administration.models import AcademicYear, Term
from finance.models import (
    FeeApplicability,
    FeeRecurrence,
    FeeStructure,
    StudentFeeAssignment,
)

migration_0011 = importlib.import_module(
    "finance.migrations.0011_fee_recurrence_identity_constraints"
)
preflight_check = migration_0011.preflight_check_recurrence_constraints


class FeeIdentityPhase2BTests(TenantTestCase):
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
        self.term_2027_t1 = Term.objects.create(
            name="First Term 2027",
            academic_year=self.year_2027,
            start_date=date(2027, 9, 1),
            end_date=date(2027, 12, 15),
        )
        self.grade = GradeLevel.objects.update_or_create(
            system_code="PHASE2B_G1",
            defaults={"section": "PRIMARY", "default_name": "Grade 1", "sequence_order": 1},
        )[0]
        self.classroom = ClassRoom.objects.create(
            name="Phase 2B Class",
            grade_level=self.grade,
            capacity=30,
        )
        self.student_a = Student.objects.create(
            first_name="Charles",
            last_name="Babbage",
            admission_number="ADM-P2B-001",
            parent_contact="08011111111",
            is_active=True,
        )
        self.student_b = Student.objects.create(
            first_name="Grace",
            last_name="Hopper",
            admission_number="ADM-P2B-002",
            parent_contact="08022222222",
            is_active=True,
        )

    # =========================================================================
    # 1. ONE_TIME Uniqueness Guarantees (Database Level)
    # =========================================================================

    def test_01_onetime_same_student_same_key_rejected(self):
        """
        Database must reject duplicate (student, logical_fee_key) for ONE_TIME,
        even if assigned under a different FeeStructure, Term, or AcademicYear.
        """
        fee_1 = FeeStructure.objects.create(
            name="Admission Fee 2026",
            amount=Decimal("50000.00"),
            academic_year=self.year_2026,
            term=self.term_2026_t1,
            logical_fee_key="admission-fee",
            recurrence=FeeRecurrence.ONE_TIME,
        )
        fee_2 = FeeStructure.objects.create(
            name="Admission Fee 2027 (Replacement)",
            amount=Decimal("55000.00"),
            academic_year=self.year_2027,
            term=self.term_2027_t1,
            logical_fee_key="admission-fee",
            recurrence=FeeRecurrence.ONE_TIME,
        )

        # First assignment succeeds
        StudentFeeAssignment.objects.create(
            student=self.student_a,
            fee_structure=fee_1,
            term=self.term_2026_t1,
            amount_owed=Decimal("50000.00"),
            logical_fee_key="admission-fee",
            recurrence=FeeRecurrence.ONE_TIME,
            academic_year=self.year_2026,
        )

        # Second assignment for same student + same key must be rejected by PostgreSQL
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                StudentFeeAssignment.objects.create(
                    student=self.student_a,
                    fee_structure=fee_2,
                    term=self.term_2027_t1,
                    amount_owed=Decimal("55000.00"),
                    logical_fee_key="admission-fee",
                    recurrence=FeeRecurrence.ONE_TIME,
                    academic_year=self.year_2027,
                )

    def test_02_onetime_different_student_allowed(self):
        """
        Different students may each have their own ONE_TIME assignment for the same key.
        """
        fee = FeeStructure.objects.create(
            name="Matriculation Fee",
            amount=Decimal("25000.00"),
            academic_year=self.year_2026,
            term=self.term_2026_t1,
            logical_fee_key="matriculation-fee",
            recurrence=FeeRecurrence.ONE_TIME,
        )

        assign_a = StudentFeeAssignment.objects.create(
            student=self.student_a,
            fee_structure=fee,
            term=self.term_2026_t1,
            amount_owed=Decimal("25000.00"),
            logical_fee_key="matriculation-fee",
            recurrence=FeeRecurrence.ONE_TIME,
            academic_year=self.year_2026,
        )
        assign_b = StudentFeeAssignment.objects.create(
            student=self.student_b,
            fee_structure=fee,
            term=self.term_2026_t1,
            amount_owed=Decimal("25000.00"),
            logical_fee_key="matriculation-fee",
            recurrence=FeeRecurrence.ONE_TIME,
            academic_year=self.year_2026,
        )
        self.assertNotEqual(assign_a.pk, assign_b.pk)

    def test_03_onetime_different_logical_fee_allowed_for_same_student(self):
        """
        Same student may receive separate ONE_TIME obligations for distinct logical fee keys.
        """
        fee_adm = FeeStructure.objects.create(
            name="Admission Fee",
            amount=Decimal("40000.00"),
            academic_year=self.year_2026,
            logical_fee_key="admission-fee",
            recurrence=FeeRecurrence.ONE_TIME,
        )
        fee_grad = FeeStructure.objects.create(
            name="Graduation Gown",
            amount=Decimal("20000.00"),
            academic_year=self.year_2026,
            logical_fee_key="graduation-gown",
            recurrence=FeeRecurrence.ONE_TIME,
        )

        StudentFeeAssignment.objects.create(
            student=self.student_a,
            fee_structure=fee_adm,
            term=self.term_2026_t1,
            amount_owed=Decimal("40000.00"),
            logical_fee_key="admission-fee",
            recurrence=FeeRecurrence.ONE_TIME,
            academic_year=self.year_2026,
        )
        assign_grad = StudentFeeAssignment.objects.create(
            student=self.student_a,
            fee_structure=fee_grad,
            term=self.term_2026_t1,
            amount_owed=Decimal("20000.00"),
            logical_fee_key="graduation-gown",
            recurrence=FeeRecurrence.ONE_TIME,
            academic_year=self.year_2026,
        )
        self.assertEqual(assign_grad.logical_fee_key, "graduation-gown")

    # =========================================================================
    # 2. ANNUAL Uniqueness Guarantees (Database Level)
    # =========================================================================

    def test_04_annual_same_student_same_key_same_year_rejected(self):
        """
        Database must reject duplicate (student, logical_fee_key, academic_year) for ANNUAL,
        even if assigned under a different Term or FeeStructure.
        """
        fee_t1 = FeeStructure.objects.create(
            name="Development Levy Term 1",
            amount=Decimal("30000.00"),
            academic_year=self.year_2026,
            term=self.term_2026_t1,
            logical_fee_key="development-levy",
            recurrence=FeeRecurrence.ANNUAL,
        )
        fee_t2 = FeeStructure.objects.create(
            name="Development Levy Term 2",
            amount=Decimal("30000.00"),
            academic_year=self.year_2026,
            term=self.term_2026_t2,
            logical_fee_key="development-levy",
            recurrence=FeeRecurrence.ANNUAL,
        )

        StudentFeeAssignment.objects.create(
            student=self.student_a,
            fee_structure=fee_t1,
            term=self.term_2026_t1,
            amount_owed=Decimal("30000.00"),
            logical_fee_key="development-levy",
            recurrence=FeeRecurrence.ANNUAL,
            academic_year=self.year_2026,
        )

        # Attempting second assignment in same academic year must fail
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                StudentFeeAssignment.objects.create(
                    student=self.student_a,
                    fee_structure=fee_t2,
                    term=self.term_2026_t2,
                    amount_owed=Decimal("30000.00"),
                    logical_fee_key="development-levy",
                    recurrence=FeeRecurrence.ANNUAL,
                    academic_year=self.year_2026,
                )

    def test_05_annual_different_year_allowed_for_same_student(self):
        """
        Same student is permitted an ANNUAL fee in a different academic year.
        """
        fee_y1 = FeeStructure.objects.create(
            name="PTA Levy 2026",
            amount=Decimal("15000.00"),
            academic_year=self.year_2026,
            logical_fee_key="pta-levy",
            recurrence=FeeRecurrence.ANNUAL,
        )
        fee_y2 = FeeStructure.objects.create(
            name="PTA Levy 2027",
            amount=Decimal("18000.00"),
            academic_year=self.year_2027,
            logical_fee_key="pta-levy",
            recurrence=FeeRecurrence.ANNUAL,
        )

        StudentFeeAssignment.objects.create(
            student=self.student_a,
            fee_structure=fee_y1,
            term=self.term_2026_t1,
            amount_owed=Decimal("15000.00"),
            logical_fee_key="pta-levy",
            recurrence=FeeRecurrence.ANNUAL,
            academic_year=self.year_2026,
        )
        assign_y2 = StudentFeeAssignment.objects.create(
            student=self.student_a,
            fee_structure=fee_y2,
            term=self.term_2027_t1,
            amount_owed=Decimal("18000.00"),
            logical_fee_key="pta-levy",
            recurrence=FeeRecurrence.ANNUAL,
            academic_year=self.year_2027,
        )
        self.assertEqual(assign_y2.academic_year, self.year_2027)

    def test_06_annual_different_student_same_year_allowed(self):
        """
        Different students may receive the same ANNUAL fee in the same academic year.
        """
        fee = FeeStructure.objects.create(
            name="Tech Infrastructure Levy",
            amount=Decimal("20000.00"),
            academic_year=self.year_2026,
            logical_fee_key="tech-levy",
            recurrence=FeeRecurrence.ANNUAL,
        )

        assign_a = StudentFeeAssignment.objects.create(
            student=self.student_a,
            fee_structure=fee,
            term=self.term_2026_t1,
            amount_owed=Decimal("20000.00"),
            logical_fee_key="tech-levy",
            recurrence=FeeRecurrence.ANNUAL,
            academic_year=self.year_2026,
        )
        assign_b = StudentFeeAssignment.objects.create(
            student=self.student_b,
            fee_structure=fee,
            term=self.term_2026_t1,
            amount_owed=Decimal("20000.00"),
            logical_fee_key="tech-levy",
            recurrence=FeeRecurrence.ANNUAL,
            academic_year=self.year_2026,
        )
        self.assertNotEqual(assign_a.pk, assign_b.pk)

    # =========================================================================
    # 3. Incomplete / Blank Identity Metadata Compatibility
    # =========================================================================

    def test_07_onetime_blank_logical_key_does_not_trigger_constraint(self):
        """
        For legacy compatibility, assignments with logical_fee_key='' are excluded
        from the conditional ONE_TIME constraint.
        """
        fee = FeeStructure.objects.create(
            name="Legacy Incomplete Fee",
            amount=Decimal("10000.00"),
            academic_year=self.year_2026,
            logical_fee_key="",
        )
        assign_1 = StudentFeeAssignment.objects.create(
            student=self.student_a,
            fee_structure=fee,
            term=self.term_2026_t1,
            amount_owed=Decimal("10000.00"),
            logical_fee_key="",
            recurrence=FeeRecurrence.ONE_TIME,
        )
        assign_2 = StudentFeeAssignment.objects.create(
            student=self.student_a,
            fee_structure=fee,
            term=self.term_2026_t2,
            amount_owed=Decimal("10000.00"),
            logical_fee_key="",
            recurrence=FeeRecurrence.ONE_TIME,
        )
        self.assertNotEqual(assign_1.pk, assign_2.pk)

    def test_08_annual_blank_key_or_null_year_does_not_trigger_constraint(self):
        """
        Assignments with logical_fee_key='' or academic_year=None are excluded
        from the conditional ANNUAL constraint for migration safety.
        """
        fee = FeeStructure.objects.create(
            name="Legacy Partial Fee",
            amount=Decimal("12000.00"),
            academic_year=self.year_2026,
            logical_fee_key="legacy-partial",
        )
        # Both have null academic_year
        assign_1 = StudentFeeAssignment.objects.create(
            student=self.student_a,
            fee_structure=fee,
            term=self.term_2026_t1,
            amount_owed=Decimal("12000.00"),
            logical_fee_key="legacy-partial",
            recurrence=FeeRecurrence.ANNUAL,
            academic_year=None,
        )
        assign_2 = StudentFeeAssignment.objects.create(
            student=self.student_a,
            fee_structure=fee,
            term=self.term_2026_t2,
            amount_owed=Decimal("12000.00"),
            logical_fee_key="legacy-partial",
            recurrence=FeeRecurrence.ANNUAL,
            academic_year=None,
        )
        self.assertNotEqual(assign_1.pk, assign_2.pk)

    # =========================================================================
    # 4. PER_TERM Unchanged
    # =========================================================================

    def test_09_per_term_uniqueness_protection_unchanged(self):
        """
        Historical (student, fee_structure, term) uniqueness constraint remains enforced,
        and multiple terms in the same academic year remain valid for PER_TERM.
        """
        fee = FeeStructure.objects.create(
            name="Standard Tuition",
            amount=Decimal("60000.00"),
            academic_year=self.year_2026,
            logical_fee_key="standard-tuition",
            recurrence=FeeRecurrence.PER_TERM,
        )
        # Term 1
        assign_t1 = StudentFeeAssignment.objects.create(
            student=self.student_a,
            fee_structure=fee,
            term=self.term_2026_t1,
            amount_owed=Decimal("60000.00"),
            logical_fee_key="standard-tuition",
            recurrence=FeeRecurrence.PER_TERM,
            academic_year=self.year_2026,
        )
        # Term 2 succeeds for PER_TERM
        assign_t2 = StudentFeeAssignment.objects.create(
            student=self.student_a,
            fee_structure=fee,
            term=self.term_2026_t2,
            amount_owed=Decimal("60000.00"),
            logical_fee_key="standard-tuition",
            recurrence=FeeRecurrence.PER_TERM,
            academic_year=self.year_2026,
        )
        self.assertNotEqual(assign_t1.pk, assign_t2.pk)

        # Duplicate in Term 1 must be rejected by unique_together
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                StudentFeeAssignment.objects.create(
                    student=self.student_a,
                    fee_structure=fee,
                    term=self.term_2026_t1,
                    amount_owed=Decimal("60000.00"),
                    logical_fee_key="standard-tuition",
                    recurrence=FeeRecurrence.PER_TERM,
                    academic_year=self.year_2026,
                )

    # =========================================================================
    # 5. Migration Preflight on Clean Data
    # =========================================================================

    def test_10_preflight_passes_on_clean_data(self):
        """
        Preflight validation succeeds without error when no conflict groups exist.
        """
        fee = FeeStructure.objects.create(
            name="Clean Fee",
            amount=Decimal("10000.00"),
            academic_year=self.year_2026,
            logical_fee_key="clean-fee",
            recurrence=FeeRecurrence.ONE_TIME,
        )
        StudentFeeAssignment.objects.create(
            student=self.student_a,
            fee_structure=fee,
            term=self.term_2026_t1,
            amount_owed=Decimal("10000.00"),
            logical_fee_key="clean-fee",
            recurrence=FeeRecurrence.ONE_TIME,
            academic_year=self.year_2026,
        )

        with connection.schema_editor() as editor:
            preflight_check(django_apps, editor)


class FeeIdentityPhase2BPreflightMigrationTests(TenantTransactionTestCase):
    """
    Tests migration preflight conflict detection using connection.schema_editor()
    to temporarily remove only the target constraint, create conflicting legacy fixtures,
    verify that preflight halts with ValidationError, and restore the constraint.
    """

    def setUp(self):
        super().setUp()
        self.year = AcademicYear.objects.create(
            name="2026/2027 Preflight",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 7, 31),
            active_year=True,
        )
        self.term_1 = Term.objects.create(
            name="Term 1 Preflight",
            academic_year=self.year,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 15),
        )
        self.term_2 = Term.objects.create(
            name="Term 2 Preflight",
            academic_year=self.year,
            start_date=date(2027, 1, 10),
            end_date=date(2027, 4, 10),
        )
        self.student = Student.objects.create(
            first_name="Ada",
            last_name="Preflight",
            admission_number="ADM-PFL-001",
            parent_contact="08011112222",
            is_active=True,
        )

    def tearDown(self):
        try:
            # Ensure any collision rows are deleted
            StudentFeeAssignment.objects.filter(
                logical_fee_key__startswith="dup-"
            ).delete()
            # Ensure constraints are restored if accidentally missing
            with connection.schema_editor() as editor:
                for c_name in [
                    "finance_assignment_uniq_onetime_student_key",
                    "finance_assignment_uniq_annual_student_key_year",
                ]:
                    constraint = next(
                        (c for c in StudentFeeAssignment._meta.constraints if c.name == c_name),
                        None,
                    )
                    if constraint:
                        try:
                            editor.add_constraint(StudentFeeAssignment, constraint)
                        except Exception:
                            pass
        finally:
            super().tearDown()

    def test_11_preflight_fails_on_onetime_duplicate(self):
        """
        When ONE_TIME duplicate collisions exist, preflight validation
        detects them and halts with ValidationError.
        """
        fee_1 = FeeStructure.objects.create(
            name="Admission Fee Preflight 1",
            amount=Decimal("10000.00"),
            academic_year=self.year,
            term=self.term_1,
            logical_fee_key="dup-onetime-collision",
            recurrence=FeeRecurrence.ONE_TIME,
            is_mandatory=False,
        )
        fee_2 = FeeStructure.objects.create(
            name="Admission Fee Preflight 2",
            amount=Decimal("10000.00"),
            academic_year=self.year,
            term=self.term_2,
            logical_fee_key="dup-onetime-collision",
            recurrence=FeeRecurrence.ONE_TIME,
            is_mandatory=False,
        )

        constraint = next(
            c for c in StudentFeeAssignment._meta.constraints
            if c.name == "finance_assignment_uniq_onetime_student_key"
        )

        # 1. Temporarily remove only the ONE_TIME constraint
        with connection.schema_editor() as editor:
            editor.remove_constraint(StudentFeeAssignment, constraint)

        try:
            # 2. Create duplicate fixtures using current models
            StudentFeeAssignment.objects.create(
                student=self.student,
                fee_structure=fee_1,
                term=self.term_1,
                amount_owed=Decimal("10000.00"),
                logical_fee_key="dup-onetime-collision",
                recurrence=FeeRecurrence.ONE_TIME,
                academic_year=self.year,
            )
            StudentFeeAssignment.objects.create(
                student=self.student,
                fee_structure=fee_2,
                term=self.term_2,
                amount_owed=Decimal("10000.00"),
                logical_fee_key="dup-onetime-collision",
                recurrence=FeeRecurrence.ONE_TIME,
                academic_year=self.year,
            )

            # 3. Invoke real migration preflight and assert ValidationError
            with connection.schema_editor() as editor:
                with self.assertRaises(ValidationError) as ctx:
                    preflight_check(django_apps, editor)

            self.assertIn("ONE_TIME collision group", str(ctx.exception))
            self.assertIn("dup-onetime-collision", str(ctx.exception))
            self.assertIn(str(self.student.id), str(ctx.exception))
        finally:
            # 4. Clean up duplicate fixtures BEFORE restoring constraint
            StudentFeeAssignment.objects.filter(
                logical_fee_key="dup-onetime-collision"
            ).delete()
            # 5. Restore the ONE_TIME constraint
            with connection.schema_editor() as editor:
                editor.add_constraint(StudentFeeAssignment, constraint)

    def test_12_preflight_fails_on_annual_duplicate(self):
        """
        When ANNUAL duplicate collisions exist in the same academic year,
        preflight validation detects them and halts with ValidationError.
        """
        fee_1 = FeeStructure.objects.create(
            name="Dev Levy Preflight 1",
            amount=Decimal("15000.00"),
            academic_year=self.year,
            term=self.term_1,
            logical_fee_key="dup-annual-collision",
            recurrence=FeeRecurrence.ANNUAL,
            is_mandatory=False,
        )
        fee_2 = FeeStructure.objects.create(
            name="Dev Levy Preflight 2",
            amount=Decimal("15000.00"),
            academic_year=self.year,
            term=self.term_2,
            logical_fee_key="dup-annual-collision",
            recurrence=FeeRecurrence.ANNUAL,
            is_mandatory=False,
        )

        constraint = next(
            c for c in StudentFeeAssignment._meta.constraints
            if c.name == "finance_assignment_uniq_annual_student_key_year"
        )

        # 1. Temporarily remove only the ANNUAL constraint
        with connection.schema_editor() as editor:
            editor.remove_constraint(StudentFeeAssignment, constraint)

        try:
            # 2. Create duplicate fixtures using current models
            StudentFeeAssignment.objects.create(
                student=self.student,
                fee_structure=fee_1,
                term=self.term_1,
                amount_owed=Decimal("15000.00"),
                logical_fee_key="dup-annual-collision",
                recurrence=FeeRecurrence.ANNUAL,
                academic_year=self.year,
            )
            StudentFeeAssignment.objects.create(
                student=self.student,
                fee_structure=fee_2,
                term=self.term_2,
                amount_owed=Decimal("15000.00"),
                logical_fee_key="dup-annual-collision",
                recurrence=FeeRecurrence.ANNUAL,
                academic_year=self.year,
            )

            # 3. Invoke real migration preflight and assert ValidationError
            with connection.schema_editor() as editor:
                with self.assertRaises(ValidationError) as ctx:
                    preflight_check(django_apps, editor)

            self.assertIn("ANNUAL collision group", str(ctx.exception))
            self.assertIn("dup-annual-collision", str(ctx.exception))
            self.assertIn(str(self.student.id), str(ctx.exception))
        finally:
            # 4. Clean up duplicate fixtures BEFORE restoring constraint
            StudentFeeAssignment.objects.filter(
                logical_fee_key="dup-annual-collision"
            ).delete()
            # 5. Restore the ANNUAL constraint
            with connection.schema_editor() as editor:
                editor.add_constraint(StudentFeeAssignment, constraint)
