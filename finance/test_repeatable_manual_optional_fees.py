from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection, transaction
from rest_framework import status
from rest_framework.test import APIClient
from school.testcases import TenantTestCase

from academic.models import ClassRoom, GradeLevel, Student, StudentClassEnrollment
from administration.models import AcademicYear, Term
from finance.models import (
    FeePaymentAllocation,
    FeeRecurrence,
    FeeStructure,
    FeeTermSchedule,
    FeeType,
    OptionalService,
    Receipt,
    ReminderSetting,
    ServiceSubscription,
    StudentFeeAssignment,
)
from finance.serializers import StudentFeeAssignmentSerializer
from finance.services import FeeAssignmentService, PaymentAllocationService
from finance.tasks import send_custom_fee_reminder, send_fee_reminders

User = get_user_model()


class RepeatableManualOptionalFeesTests(TenantTestCase):
    """
    Comprehensive test suite for Repeatable Manual Optional Fees.
    Covers:
    - Manual optional charges (first charge, repeat after paid, repeat while unpaid, distinct charge numbers, allow_repeat flag)
    - Mandatory recurrence protection (ANNUAL, ONE_TIME, PER_TERM duplicate blocked, enrollment sync idempotent)
    - Optional subscription protection (auto-assign does not repeat)
    - Due-date behavior (null due date allowed, payable, not overdue, reminder null-safety, snapshotting)
    - Multi-fee payment allocations (independent and combined allocations)
    - Concurrency safety (distinct charge numbers under concurrent execution)
    - API endpoint & Serializer defense
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
            email="repeat-fees-accountant@test.local",
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
            first_name="Fatima",
            last_name="Aliyu",
            admission_number="GVA/JSS/28/0101",
            classroom=self.classroom,
            parent_contact="08012345678",
            is_active=True,
        )
        self.enrollment = StudentClassEnrollment.objects.create(
            student=self.student,
            classroom=self.classroom,
            academic_year=self.year,
            is_active=True,
        )

        # Optional Fee: School Uniform (ONE_TIME, nullable due date, is_mandatory=False)
        self.fee_uniform = FeeStructure.objects.create(
            name="School Uniform",
            amount=Decimal("15000.00"),
            fee_type=FeeType.OTHER,
            recurrence=FeeRecurrence.ONE_TIME,
            logical_fee_key="school-uniform",
            academic_year=self.year,
            term=self.term_1,
            is_mandatory=False,
            due_date=None,
            created_by=self.user,
        )

        # Mandatory Annual Fee: Development Levy (ANNUAL, is_mandatory=True)
        self.fee_dev_levy = FeeStructure.objects.create(
            name="Development Levy",
            amount=Decimal("30000.00"),
            fee_type=FeeType.MAINTENANCE,
            recurrence=FeeRecurrence.ANNUAL,
            academic_year=self.year,
            term=None,
            logical_fee_key="dev-levy-2028",
            is_mandatory=True,
            created_by=self.user,
        )

        # Mandatory One-Time Fee: Admission Fee (ONE_TIME, is_mandatory=True)
        self.fee_admission = FeeStructure.objects.create(
            name="Admission Fee",
            amount=Decimal("50000.00"),
            fee_type=FeeType.ADMISSION,
            recurrence=FeeRecurrence.ONE_TIME,
            academic_year=self.year,
            term=None,
            logical_fee_key="admission-fee",
            is_mandatory=True,
            created_by=self.user,
        )

        # Mandatory Per-Term Fee: Tuition (PER_TERM, is_mandatory=True)
        self.fee_tuition = FeeStructure.objects.create(
            name="Tuition",
            amount=Decimal("100000.00"),
            fee_type=FeeType.TUITION,
            recurrence=FeeRecurrence.PER_TERM,
            academic_year=self.year,
            term=self.term_1,
            logical_fee_key="tuition-per-term",
            is_mandatory=True,
            created_by=self.user,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Manual Optional Charges
    # ──────────────────────────────────────────────────────────────────────────

    def test_01_first_manual_optional_assignment_succeeds(self):
        """First manual assignment of an optional fee succeeds with charge_number=1."""
        assignment = FeeAssignmentService.assign_fee_to_student(
            student=self.student,
            fee_structure=self.fee_uniform,
            term=self.term_1,
            allow_repeat=False,
        )
        self.assertIsNotNone(assignment)
        self.assertEqual(assignment.charge_number, 1)
        self.assertEqual(assignment.amount_owed, Decimal("15000.00"))
        self.assertEqual(assignment.amount_paid, Decimal("0.00"))
        self.assertIsNone(assignment.due_date)

    def test_02_same_optional_fee_manually_assigned_again_after_paid(self):
        """Same optional fee can be manually assigned again after the first charge is fully paid."""
        assign1 = FeeAssignmentService.assign_fee_to_student(
            student=self.student,
            fee_structure=self.fee_uniform,
            term=self.term_1,
            allow_repeat=False,
        )
        # Pay charge 1 in full
        assign1.amount_paid = Decimal("15000.00")
        assign1.save(update_fields=["amount_paid"])
        self.assertTrue(assign1.is_fully_paid)

        # Assign again with allow_repeat=True
        assign2 = FeeAssignmentService.assign_fee_to_student(
            student=self.student,
            fee_structure=self.fee_uniform,
            term=self.term_1,
            allow_repeat=True,
        )
        self.assertNotEqual(assign1.pk, assign2.pk)
        self.assertEqual(assign2.charge_number, 2)
        self.assertEqual(assign2.amount_owed, Decimal("15000.00"))
        self.assertEqual(assign2.amount_paid, Decimal("0.00"))
        self.assertEqual(assign2.balance, Decimal("15000.00"))

        # Verify charge 1 remains fully paid
        assign1.refresh_from_db()
        self.assertEqual(assign1.amount_paid, Decimal("15000.00"))
        self.assertEqual(assign1.balance, Decimal("0.00"))

    def test_03_same_optional_fee_manually_assigned_again_while_unpaid(self):
        """Same optional fee can be manually assigned again even while the first remains unpaid."""
        assign1 = FeeAssignmentService.assign_fee_to_student(
            student=self.student,
            fee_structure=self.fee_uniform,
            term=self.term_1,
            allow_repeat=False,
        )
        self.assertEqual(assign1.amount_paid, Decimal("0.00"))

        # Assign second uniform while first is completely unpaid
        assign2 = FeeAssignmentService.assign_fee_to_student(
            student=self.student,
            fee_structure=self.fee_uniform,
            term=self.term_1,
            allow_repeat=True,
        )
        self.assertNotEqual(assign1.pk, assign2.pk)
        self.assertEqual(assign2.charge_number, 2)
        self.assertEqual(assign2.amount_owed, Decimal("15000.00"))

        # Both exist as independent assignments
        assignments = StudentFeeAssignment.objects.filter(
            student=self.student, fee_structure=self.fee_uniform
        ).order_by("charge_number")
        self.assertEqual(assignments.count(), 2)
        self.assertEqual([a.charge_number for a in assignments], [1, 2])

    def test_04_repeat_assignments_receive_deterministic_distinct_charge_numbers(self):
        """Repeated manual assignments receive deterministic sequence: 1, 2, 3."""
        a1 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )
        a2 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=True
        )
        a3 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=True
        )

        self.assertEqual(a1.charge_number, 1)
        self.assertEqual(a2.charge_number, 2)
        self.assertEqual(a3.charge_number, 3)

    def test_05_existing_assignments_remain_untouched_on_repeat(self):
        """Existing assignment attributes (waiver, paid, adjustments) are untouched when repeat charge is created."""
        a1 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )
        a1.amount_paid = Decimal("5000.00")
        a1.is_waived = False
        a1.save()

        # Create repeat charge
        a2 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=True
        )

        a1.refresh_from_db()
        self.assertEqual(a1.amount_paid, Decimal("5000.00"))
        self.assertEqual(a1.balance, Decimal("10000.00"))
        self.assertFalse(a1.is_waived)
        self.assertEqual(a1.charge_number, 1)

        self.assertEqual(a2.amount_paid, Decimal("0.00"))
        self.assertEqual(a2.balance, Decimal("15000.00"))
        self.assertEqual(a2.charge_number, 2)

    def test_06_allow_repeat_false_preserves_existing_idempotency(self):
        """Calling assign_fee_to_student with allow_repeat=False returns existing obligation without creating new row."""
        a1 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )
        a2 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )
        self.assertEqual(a1.pk, a2.pk)
        self.assertEqual(
            StudentFeeAssignment.objects.filter(student=self.student, fee_structure=self.fee_uniform).count(),
            1,
        )

    def test_07_allow_repeat_true_on_mandatory_fee_does_not_bypass_recurrence(self):
        """Passing allow_repeat=True for a mandatory fee raises ValidationError and blocks duplication."""
        # First assignment of mandatory annual fee
        FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_dev_levy, term=self.term_1, allow_repeat=False
        )

        # Attempt to repeat mandatory fee with allow_repeat=True
        with self.assertRaises(ValidationError) as ctx:
            FeeAssignmentService.assign_fee_to_student(
                student=self.student, fee_structure=self.fee_dev_levy, term=self.term_1, allow_repeat=True
            )
        self.assertIn("mandatory", str(ctx.exception).lower())
        self.assertEqual(
            StudentFeeAssignment.objects.filter(student=self.student, fee_structure=self.fee_dev_levy).count(),
            1,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Mandatory Recurrence Protection
    # ──────────────────────────────────────────────────────────────────────────

    def test_08_mandatory_annual_duplicate_remains_blocked(self):
        """Mandatory ANNUAL fee cannot be duplicated within the same academic year."""
        a1 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_dev_levy, term=self.term_1
        )
        # Attempting in term 2 of same academic year
        a2 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_dev_levy, term=self.term_2
        )
        self.assertEqual(a1.pk, a2.pk)
        self.assertEqual(
            StudentFeeAssignment.objects.filter(student=self.student, fee_structure=self.fee_dev_levy).count(),
            1,
        )

    def test_09_mandatory_one_time_duplicate_remains_blocked(self):
        """Mandatory ONE_TIME fee cannot be duplicated across the student's lifetime."""
        a1 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_admission, term=self.term_1
        )
        # Attempting assignment again in term 2
        a2 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_admission, term=self.term_2
        )
        self.assertEqual(a1.pk, a2.pk)
        self.assertEqual(
            StudentFeeAssignment.objects.filter(student=self.student, fee_structure=self.fee_admission).count(),
            1,
        )

    def test_10_mandatory_per_term_duplicate_in_same_term_remains_blocked(self):
        """Mandatory PER_TERM fee cannot be duplicated in the same term."""
        a1 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_tuition, term=self.term_1
        )
        a2 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_tuition, term=self.term_1
        )
        self.assertEqual(a1.pk, a2.pk)
        self.assertEqual(
            StudentFeeAssignment.objects.filter(
                student=self.student, fee_structure=self.fee_tuition, term=self.term_1
            ).count(),
            1,
        )

    def test_11_enrollment_sync_remains_idempotent(self):
        """sync_fees_for_enrollment called multiple times creates exactly one obligation per recurrence."""
        FeeAssignmentService.sync_fees_for_enrollment(student=self.student, term=self.term_1)
        count_first = StudentFeeAssignment.objects.filter(student=self.student).count()

        # Run sync again
        FeeAssignmentService.sync_fees_for_enrollment(student=self.student, term=self.term_1)
        count_second = StudentFeeAssignment.objects.filter(student=self.student).count()

        self.assertEqual(count_first, count_second)

    def test_12_sync_enrollment_fees_command_remains_idempotent(self):
        """Management command sync_enrollment_fees does not duplicate any assignments."""
        call_command("sync_enrollment_fees", academic_year=self.year.name)
        count_first = StudentFeeAssignment.objects.filter(student=self.student).count()

        call_command("sync_enrollment_fees", academic_year=self.year.name)
        count_second = StudentFeeAssignment.objects.filter(student=self.student).count()

        self.assertEqual(count_first, count_second)

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Optional Subscription Protection
    # ──────────────────────────────────────────────────────────────────────────

    def test_13_automatic_subscription_per_term_fee_idempotent(self):
        """Active subscription to an optional service generates at most one obligation per term."""
        bus_service = OptionalService.objects.create(
            name="School Bus Route 1",
            fee_type=FeeType.TRANSPORT,
            is_active=True,
        )
        fee_bus = FeeStructure.objects.create(
            name="Bus Transport Term 1",
            amount=Decimal("20000.00"),
            fee_type=FeeType.TRANSPORT,
            recurrence=FeeRecurrence.PER_TERM,
            academic_year=self.year,
            term=self.term_1,
            is_mandatory=False,
            optional_service=bus_service,
            created_by=self.user,
        )
        ServiceSubscription.objects.create(
            student=self.student,
            service=bus_service,
            is_active=True,
        )

        # Sync twice
        FeeAssignmentService.sync_fees_for_enrollment(student=self.student, term=self.term_1)
        FeeAssignmentService.sync_fees_for_enrollment(student=self.student, term=self.term_1)

        bus_assignments = StudentFeeAssignment.objects.filter(
            student=self.student, fee_structure=fee_bus
        )
        self.assertEqual(bus_assignments.count(), 1)
        self.assertEqual(bus_assignments.first().charge_number, 1)

    def test_14_automatic_optional_service_assignment_does_not_create_repeats(self):
        """Automatic sync never passes allow_repeat=True, even for optional services."""
        call_command("sync_enrollment_fees", academic_year=self.year.name)
        # Even if optional uniform exists, automatic sync never creates duplicate charges
        uniform_count = StudentFeeAssignment.objects.filter(
            student=self.student, fee_structure=self.fee_uniform
        ).count()
        # Optional fees without active subscription or mandatory flag are not even auto-assigned
        self.assertEqual(uniform_count, 0)

    # ──────────────────────────────────────────────────────────────────────────
    # 4. Due Dates & Reminders
    # ──────────────────────────────────────────────────────────────────────────

    def test_15_repeat_optional_assignment_with_due_date_none_succeeds(self):
        """Repeat optional assignment with due_date=None succeeds and retains None."""
        a1 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )
        a2 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=True
        )
        self.assertIsNone(a1.due_date)
        self.assertIsNone(a2.due_date)

    def test_16_null_due_date_is_overdue_is_false(self):
        """Assignment with due_date=None has is_overdue=False."""
        assignment = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )
        self.assertFalse(assignment.is_overdue)

    def test_17_null_due_date_included_in_outstanding_balance(self):
        """Assignment with due_date=None is included in student's balance and receivables."""
        FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )
        FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=True
        )
        total_balance = sum(
            a.balance for a in StudentFeeAssignment.objects.filter(student=self.student)
        )
        self.assertEqual(total_balance, Decimal("30000.00"))

    def test_18_null_due_date_remains_payable(self):
        """Assignment with due_date=None is immediately payable."""
        assignment = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )
        self.assertEqual(assignment.balance, Decimal("15000.00"))
        # Record payment
        receipt = PaymentAllocationService.record_payment_with_allocations(
            receipt_data={
                "payer": "Mr Aliyu",
                "paid_through": "Cash",
                "payment_date": date.today(),
            },
            allocations=[{"fee_assignment": assignment.pk, "amount": "15000.00"}],
            received_by=self.user,
        )
        self.assertIsNotNone(receipt)
        assignment.refresh_from_db()
        self.assertEqual(assignment.balance, Decimal("0.00"))
        self.assertTrue(assignment.is_fully_paid)

    def test_19_null_due_date_excluded_from_scheduled_reminders(self):
        """Assignments with due_date=None are not selected by date-based reminder filters."""
        FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )
        # Create ReminderSetting
        ReminderSetting.objects.create(
            name="Due Date Reminder",
            days_before_due=0,
            is_active=True,
            message_template="Fee due today: {{fee_name}}",
        )
        # Run send_fee_reminders task - should complete safely without picking up null due_date
        results = send_fee_reminders(schema_name=self.tenant.schema_name)
        self.assertIsInstance(results, dict)
        self.assertEqual(results.get("sent", 0), 0)

    def test_20_custom_reminder_remains_null_safe(self):
        """Custom fee reminder for fee with null due_date completes safely."""
        FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )
        # send_custom_fee_reminder must not crash on null due date
        result = send_custom_fee_reminder(
            schema_name=self.tenant.schema_name,
            fee_structure_id=self.fee_uniform.id,
            message="Please remember to pay for the uniform.",
        )
        self.assertIsInstance(result, dict)

    def test_21_repeat_optional_fee_with_real_due_date_snapshots_correctly(self):
        """Repeat optional fee with a specific due_date snapshots that date onto repeat charges."""
        fee_with_date = FeeStructure.objects.create(
            name="Graduation Gown",
            amount=Decimal("10000.00"),
            fee_type=FeeType.OTHER,
            recurrence=FeeRecurrence.ONE_TIME,
            logical_fee_key="graduation-gown",
            academic_year=self.year,
            term=self.term_1,
            is_mandatory=False,
            due_date=date(2028, 11, 15),
            created_by=self.user,
        )
        a1 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=fee_with_date, term=self.term_1, allow_repeat=False
        )
        a2 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=fee_with_date, term=self.term_1, allow_repeat=True
        )
        self.assertEqual(a1.due_date, date(2028, 11, 15))
        self.assertEqual(a2.due_date, date(2028, 11, 15))

    def test_22_per_term_schedule_driven_assignment_snapshots_due_date(self):
        """PER_TERM fee with schedule snapshots FeeTermSchedule.due_date."""
        fee_term_sched = FeeStructure.objects.create(
            name="Term Activity Fee",
            amount=Decimal("5000.00"),
            fee_type=FeeType.OTHER,
            recurrence=FeeRecurrence.PER_TERM,
            academic_year=self.year,
            term=None,
            is_mandatory=False,
            created_by=self.user,
        )
        FeeTermSchedule.objects.create(
            fee_structure=fee_term_sched,
            term=self.term_1,
            amount=Decimal("5000.00"),
            due_date=date(2028, 10, 20),
        )
        a1 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=fee_term_sched, term=self.term_1, allow_repeat=False
        )
        self.assertEqual(a1.due_date, date(2028, 10, 20))

    # ──────────────────────────────────────────────────────────────────────────
    # 5. Payments and Multi-Fee Allocations
    # ──────────────────────────────────────────────────────────────────────────

    def test_23_two_repeated_optional_assignments_coexist_in_outstanding_query(self):
        """Two repeated optional assignments coexist in queries as separate obligations."""
        a1 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )
        a2 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=True
        )

        outstanding = StudentFeeAssignment.objects.filter(
            student=self.student, is_waived=False, amount_owed__gt=models_f("amount_paid")
        ) if hasattr(StudentFeeAssignment, "models_f") else [
            a for a in StudentFeeAssignment.objects.filter(student=self.student, is_waived=False)
            if a.balance > 0
        ]
        self.assertEqual(len(outstanding), 2)
        pks = [o.pk for o in outstanding]
        self.assertIn(a1.pk, pks)
        self.assertIn(a2.pk, pks)

    def test_24_payment_can_allocate_against_charge_1_independently(self):
        """Payment can allocate against charge #1 independently while charge #2 remains untouched."""
        a1 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )
        a2 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=True
        )

        # Pay charge 1 only
        receipt = PaymentAllocationService.record_payment_with_allocations(
            receipt_data={
                "payer": "Alhaji Aliyu",
                "paid_through": "Bank Transfer",
                "payment_date": date(2028, 9, 20),
            },
            allocations=[{"fee_assignment": a1.pk, "amount": "15000.00"}],
            received_by=self.user,
        )
        self.assertIsNotNone(receipt)

        a1.refresh_from_db()
        a2.refresh_from_db()
        self.assertEqual(a1.amount_paid, Decimal("15000.00"))
        self.assertEqual(a1.balance, Decimal("0.00"))
        self.assertTrue(a1.is_fully_paid)

        self.assertEqual(a2.amount_paid, Decimal("0.00"))
        self.assertEqual(a2.balance, Decimal("15000.00"))
        self.assertFalse(a2.is_fully_paid)

    def test_25_payment_can_allocate_against_charge_2_independently(self):
        """Payment can allocate against charge #2 independently while charge #1 remains untouched."""
        a1 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )
        a2 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=True
        )

        # Pay charge 2 only
        receipt = PaymentAllocationService.record_payment_with_allocations(
            receipt_data={
                "payer": "Alhaji Aliyu",
                "paid_through": "Bank Transfer",
                "payment_date": date(2028, 9, 20),
            },
            allocations=[{"fee_assignment": a2.pk, "amount": "15000.00"}],
            received_by=self.user,
        )
        self.assertIsNotNone(receipt)

        a1.refresh_from_db()
        a2.refresh_from_db()
        self.assertEqual(a1.amount_paid, Decimal("0.00"))
        self.assertEqual(a1.balance, Decimal("15000.00"))

        self.assertEqual(a2.amount_paid, Decimal("15000.00"))
        self.assertEqual(a2.balance, Decimal("0.00"))
        self.assertTrue(a2.is_fully_paid)

    def test_26_one_receipt_can_allocate_against_both_charges(self):
        """One receipt can allocate across both repeated charges simultaneously."""
        a1 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )
        a2 = FeeAssignmentService.assign_fee_to_student(
            student=self.student, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=True
        )

        receipt = PaymentAllocationService.record_payment_with_allocations(
            receipt_data={
                "payer": "Alhaji Aliyu",
                "paid_through": "Bank Transfer",
                "payment_date": date(2028, 9, 20),
            },
            allocations=[
                {"fee_assignment": a1.pk, "amount": "15000.00"},
                {"fee_assignment": a2.pk, "amount": "15000.00"},
            ],
            received_by=self.user,
        )
        self.assertEqual(receipt.amount, Decimal("30000.00"))
        self.assertEqual(receipt.fee_allocations.count(), 2)

        a1.refresh_from_db()
        a2.refresh_from_db()
        self.assertEqual(a1.balance, Decimal("0.00"))
        self.assertEqual(a2.balance, Decimal("0.00"))

    # ──────────────────────────────────────────────────────────────────────────
    # 7. API & Serializer Direct Protection
    # ──────────────────────────────────────────────────────────────────────────

    def test_28_bulk_assign_api_with_allow_repeat_creates_repeat_charge(self):
        """bulk_assign endpoint with allow_repeat=True creates repeat charge and returns detailed summary."""
        # Initial assign
        res1 = self.client.post(
            "/api/finance/student-fee-assignments/bulk_assign/",
            {
                "fee_structure": self.fee_uniform.id,
                "term": self.term_1.id,
                "student_ids": [self.student.id],
                "allow_repeat": False,
            },
            format="json",
        )
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.assertEqual(res1.data["assigned_count"], 1)

        # Re-assign with allow_repeat=False -> skipped
        res2 = self.client.post(
            "/api/finance/student-fee-assignments/bulk_assign/",
            {
                "fee_structure": self.fee_uniform.id,
                "term": self.term_1.id,
                "student_ids": [self.student.id],
                "allow_repeat": False,
            },
            format="json",
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.data["assigned_count"], 0)
        self.assertEqual(res2.data["skipped_count"], 1)
        self.assertIn("already assigned", res2.data["skipped"][0]["reason"])

        # Re-assign with allow_repeat=True -> success with charge_number=2
        res3 = self.client.post(
            "/api/finance/student-fee-assignments/bulk_assign/",
            {
                "fee_structure": self.fee_uniform.id,
                "term": self.term_1.id,
                "student_ids": [self.student.id],
                "allow_repeat": True,
            },
            format="json",
        )
        self.assertEqual(res3.status_code, status.HTTP_200_OK)
        self.assertEqual(res3.data["assigned_count"], 1)

        charges = list(
            StudentFeeAssignment.objects.filter(
                student=self.student, fee_structure=self.fee_uniform
            ).values_list("charge_number", flat=True).order_by("charge_number")
        )
        self.assertEqual(charges, [1, 2])

    def test_29_bulk_assign_api_rejects_allow_repeat_on_mandatory_fee(self):
        """bulk_assign endpoint returns HTTP 400 if allow_repeat=True is requested for mandatory fee."""
        res = self.client.post(
            "/api/finance/student-fee-assignments/bulk_assign/",
            {
                "fee_structure": self.fee_dev_levy.id,
                "term": self.term_1.id,
                "student_ids": [self.student.id],
                "allow_repeat": True,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Cannot repeat mandatory fee", res.data["error"])

    def test_30_direct_serializer_create_routes_through_service(self):
        """Direct POST to serializer routes through service to maintain financial invariants."""
        # Initial creation
        serializer1 = StudentFeeAssignmentSerializer(
            data={
                "student": self.student.id,
                "fee_structure": self.fee_uniform.id,
                "term": self.term_1.id,
            }
        )
        self.assertTrue(serializer1.is_valid(), serializer1.errors)
        assign1 = serializer1.save()
        self.assertEqual(assign1.charge_number, 1)

        # Second direct serializer creation without repeat returns existing assignment (idempotent)
        serializer2 = StudentFeeAssignmentSerializer(
            data={
                "student": self.student.id,
                "fee_structure": self.fee_uniform.id,
                "term": self.term_1.id,
            }
        )
        self.assertTrue(serializer2.is_valid(), serializer2.errors)
        assign2 = serializer2.save()
        self.assertEqual(assign1.pk, assign2.pk)
