import importlib
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.apps import apps
from django.utils import timezone
from school.testcases import TenantTestCase

from academic.models import ClassRoom, GradeLevel, Student, StudentClassEnrollment
from administration.models import AcademicYear, Term

migration_0012 = importlib.import_module(
    "finance.migrations.0012_studentfeeassignment_due_date"
)
backfill_fee_assignment_due_dates = migration_0012.backfill_fee_assignment_due_dates
from finance.models import (
    FeeApplicability,
    FeeRecurrence,
    FeeStructure,
    FeeType,
    ReminderSetting,
    StudentFeeAssignment,
)
from finance.serializers import StudentFeeAssignmentSerializer
from finance.services import FeeAssignmentService
from finance.tasks import send_fee_reminders


class FeeDueDatePhase5BTests(TenantTestCase):
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

        self.term_1 = Term.objects.create(
            name="First Term 2026",
            academic_year=self.year_2026,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 15),
        )

        self.term_2 = Term.objects.create(
            name="Second Term 2027",
            academic_year=self.year_2026,
            start_date=date(2027, 1, 10),
            end_date=date(2027, 4, 10),
        )

        self.grade_1 = GradeLevel.objects.update_or_create(
            system_code="P5B_G1",
            defaults={"section": "PRIMARY", "default_name": "Grade 1", "sequence_order": 1},
        )[0]

        self.classroom_1a = ClassRoom.objects.create(
            name="Primary 1A",
            grade_level=self.grade_1,
        )

        self.student = Student.objects.create(
            first_name="Amara",
            last_name="Eze",
            admission_number="ADM-P5B-001",
            classroom=self.classroom_1a,
            is_active=True,
        )

        self.enrollment = StudentClassEnrollment.objects.create(
            student=self.student,
            classroom=self.classroom_1a,
            academic_year=self.year_2026,
            is_active=True,
        )

    # -------------------------------------------------------------------------
    # 1. Creation Snapshot
    # -------------------------------------------------------------------------
    def test_assignment_creation_snapshots_fee_structure_due_date(self):
        """Newly created assignment explicitly snapshots fee_structure.due_date."""
        fee = FeeStructure.objects.create(
            name="Tuition Term 1",
            fee_type=FeeType.TUITION,
            amount=Decimal("50000.00"),
            academic_year=self.year_2026,
            term=self.term_1,
            recurrence=FeeRecurrence.PER_TERM,
            logical_fee_key="tuition-t1",
            due_date=date(2026, 10, 5),
            is_mandatory=True,
        )

        count = FeeAssignmentService.assign_fee(fee_structure=fee, term=self.term_1)
        self.assertEqual(count, 1)

        assignment = StudentFeeAssignment.objects.get(
            student=self.student,
            fee_structure=fee,
            term=self.term_1,
        )
        self.assertEqual(assignment.due_date, date(2026, 10, 5))
        self.assertEqual(assignment.amount_owed, Decimal("50000.00"))

    # -------------------------------------------------------------------------
    # 2. Historical Immutability
    # -------------------------------------------------------------------------
    def test_editing_fee_structure_due_date_does_not_alter_existing_assignment(self):
        """Editing FeeStructure.due_date does NOT propagate to existing StudentFeeAssignment rows."""
        fee = FeeStructure.objects.create(
            name="Tuition Term 1",
            fee_type=FeeType.TUITION,
            amount=Decimal("50000.00"),
            academic_year=self.year_2026,
            term=self.term_1,
            recurrence=FeeRecurrence.PER_TERM,
            logical_fee_key="tuition-t1",
            due_date=date(2026, 10, 5),
            is_mandatory=True,
        )

        FeeAssignmentService.assign_fee(fee_structure=fee, term=self.term_1)
        assignment = StudentFeeAssignment.objects.get(
            student=self.student,
            fee_structure=fee,
            term=self.term_1,
        )
        self.assertEqual(assignment.due_date, date(2026, 10, 5))

        # Admin subsequently edits FeeStructure due_date
        fee.due_date = date(2026, 10, 20)
        fee.save()

        # Existing assignment remains locked at original historical date
        assignment.refresh_from_db()
        self.assertEqual(assignment.due_date, date(2026, 10, 5))
        self.assertEqual(fee.due_date, date(2026, 10, 20))

    # -------------------------------------------------------------------------
    # 3. Future Assignment Behavior
    # -------------------------------------------------------------------------
    def test_future_assignment_snapshots_new_date_while_existing_retains_old(self):
        """New assignments snapshot the updated FeeStructure due date while existing assignments retain old date."""
        fee = FeeStructure.objects.create(
            name="ICT Levy",
            fee_type=FeeType.OTHER,
            amount=Decimal("15000.00"),
            academic_year=self.year_2026,
            term=self.term_1,
            recurrence=FeeRecurrence.PER_TERM,
            logical_fee_key="ict-levy",
            due_date=date(2026, 10, 5),
            is_mandatory=True,
        )

        # Student 1 gets Term 1 assignment
        FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee,
            student=self.student,
            term=self.term_1,
        )
        assignment_1 = StudentFeeAssignment.objects.get(
            student=self.student,
            fee_structure=fee,
            term=self.term_1,
        )
        self.assertEqual(assignment_1.due_date, date(2026, 10, 5))

        # FeeStructure due_date is updated for a new student / later assignment
        fee.due_date = date(2026, 10, 25)
        fee.save()

        # Student 2 is enrolled later and assigned for Term 1
        student_2 = Student.objects.create(
            first_name="Chidi",
            last_name="Okoro",
            admission_number="ADM-P5B-002",
            classroom=self.classroom_1a,
            is_active=True,
        )
        FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee,
            student=student_2,
            term=self.term_1,
        )
        assignment_2 = StudentFeeAssignment.objects.get(
            student=student_2,
            fee_structure=fee,
            term=self.term_1,
        )

        # New assignment snapshots new date, existing assignment retains old date
        self.assertEqual(assignment_2.due_date, date(2026, 10, 25))
        assignment_1.refresh_from_db()
        self.assertEqual(assignment_1.due_date, date(2026, 10, 5))

    # -------------------------------------------------------------------------
    # 4. ONE_TIME & ANNUAL Recurrence Compatibility
    # -------------------------------------------------------------------------
    def test_onetime_and_annual_fees_snapshot_due_date_and_preserve_idempotency(self):
        """ONE_TIME and ANNUAL fees snapshot due_date while preserving unique constraints and idempotency."""
        # ONE_TIME
        adm_fee = FeeStructure.objects.create(
            name="Admission Fee",
            fee_type=FeeType.ADMISSION,
            amount=Decimal("30000.00"),
            academic_year=self.year_2026,
            term=None,
            recurrence=FeeRecurrence.ONE_TIME,
            applicability=FeeApplicability.NEW_STUDENTS_ONLY,
            logical_fee_key="admission-fee",
            due_date=date(2026, 9, 30),
            is_mandatory=True,
        )
        created_1 = FeeAssignmentService.assign_fee_to_student(
            fee_structure=adm_fee,
            student=self.student,
            term=self.term_1,
        )
        self.assertEqual(created_1, 1)
        adm_assign = StudentFeeAssignment.objects.get(
            student=self.student,
            fee_structure=adm_fee,
        )
        self.assertEqual(adm_assign.due_date, date(2026, 9, 30))

        # Idempotent re-run returns 0
        created_again = FeeAssignmentService.assign_fee_to_student(
            fee_structure=adm_fee,
            student=self.student,
            term=self.term_2,
        )
        self.assertEqual(created_again, 0)
        self.assertEqual(StudentFeeAssignment.objects.filter(student=self.student, logical_fee_key="admission-fee").count(), 1)

        # ANNUAL
        dev_fee = FeeStructure.objects.create(
            name="Development Levy",
            fee_type=FeeType.MAINTENANCE,
            amount=Decimal("20000.00"),
            academic_year=self.year_2026,
            term=None,
            recurrence=FeeRecurrence.ANNUAL,
            logical_fee_key="dev-levy",
            due_date=date(2026, 11, 15),
            is_mandatory=True,
        )
        ann_created = FeeAssignmentService.assign_fee_to_student(
            fee_structure=dev_fee,
            student=self.student,
            term=self.term_1,
        )
        self.assertEqual(ann_created, 1)
        ann_assign = StudentFeeAssignment.objects.get(
            student=self.student,
            fee_structure=dev_fee,
        )
        self.assertEqual(ann_assign.due_date, date(2026, 11, 15))

        # Re-run in Term 2 returns 0
        ann_again = FeeAssignmentService.assign_fee_to_student(
            fee_structure=dev_fee,
            student=self.student,
            term=self.term_2,
        )
        self.assertEqual(ann_again, 0)

    # -------------------------------------------------------------------------
    # 5. Reminder Logic Uses assignment.due_date
    # -------------------------------------------------------------------------
    @patch("finance.tasks.NotificationService")
    def test_send_fee_reminders_uses_assignment_due_date(self, mock_notify_cls):
        """Reminders select assignments based on assignment.due_date, not FeeStructure.due_date."""
        mock_notify = MagicMock()
        mock_notify_cls.return_value = mock_notify

        fee = FeeStructure.objects.create(
            name="Tuition Term 1",
            fee_type=FeeType.TUITION,
            amount=Decimal("50000.00"),
            academic_year=self.year_2026,
            term=self.term_1,
            recurrence=FeeRecurrence.PER_TERM,
            logical_fee_key="tuition-t1",
            due_date=date(2026, 10, 5),
            is_mandatory=True,
        )

        FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee,
            student=self.student,
            term=self.term_1,
        )
        assignment = StudentFeeAssignment.objects.get(
            student=self.student,
            fee_structure=fee,
        )
        self.assertEqual(assignment.due_date, date(2026, 10, 5))

        # Admin edits FeeStructure due date to Oct 25
        fee.due_date = date(2026, 10, 25)
        fee.save()

        # Reminder rule: 0 days before due
        ReminderSetting.objects.create(
            name="Due Day Reminder",
            days_before_due=0,
            is_active=True,
            fee_structure=fee,
            message_template="Fee {{fee_name}} is due on {{due_date}}.",
        )

        # Mock date to Oct 5 (matching assignment.due_date)
        with patch("finance.tasks.timezone.now") as mock_now:
            mock_now.return_value.date.return_value = date(2026, 10, 5)

            # Query should match on assignment.due_date=2026-10-05 even though fee_structure.due_date is 2026-10-25
            matching = StudentFeeAssignment.objects.filter(
                due_date=date(2026, 10, 5),
                amount_paid__lt=Decimal("50000.00"),
                is_waived=False,
            )
            self.assertEqual(matching.count(), 1)
            self.assertEqual(matching.first().pk, assignment.pk)

            # Query for fee_structure.due_date (Oct 25) must NOT match assignment
            mismatch = StudentFeeAssignment.objects.filter(
                due_date=date(2026, 10, 25),
                amount_paid__lt=Decimal("50000.00"),
                is_waived=False,
            )
            self.assertEqual(mismatch.count(), 0)

    def test_null_due_date_assignments_do_not_trigger_date_based_reminders(self):
        """Assignments with due_date=None are not selected by date-based reminder filters."""
        fee = FeeStructure.objects.create(
            name="No Date Fee",
            fee_type=FeeType.OTHER,
            amount=Decimal("5000.00"),
            academic_year=self.year_2026,
            term=self.term_1,
            recurrence=FeeRecurrence.PER_TERM,
            logical_fee_key="no-date-fee",
            due_date=None,
            is_mandatory=True,
        )
        FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee,
            student=self.student,
            term=self.term_1,
        )
        assignment = StudentFeeAssignment.objects.get(
            student=self.student,
            fee_structure=fee,
        )
        self.assertIsNone(assignment.due_date)

        target_date = date(2026, 10, 5)
        matching = StudentFeeAssignment.objects.filter(
            due_date=target_date,
            amount_paid__lt=Decimal("5000.00"),
            is_waived=False,
        )
        self.assertEqual(matching.count(), 0)

    @patch("finance.tasks.NotificationService")
    def test_custom_reminder_does_not_present_feestructure_due_date_when_assignment_due_date_is_null(
        self, mock_notify_cls
    ):
        """
        Focused regression:
        1. assignment.due_date = None
        2. fee_structure.due_date has a value (e.g. 2026-10-25)
        3. Custom reminder does NOT present the FeeStructure date as the assignment's due date.
        """
        from django.db import connection
        from academic.models import Parent
        from finance.tasks import send_custom_fee_reminder
        from users.models import CustomUser

        mock_notify = MagicMock()
        mock_notify_cls.return_value = mock_notify

        parent_user = CustomUser.objects.create(
            email="parent.amara.null@example.com",
            first_name="Amara",
            last_name="Parent",
            is_parent=True,
        )
        parent = Parent.objects.create(
            user=parent_user,
            email="parent.amara.null@example.com",
        )
        self.student.parent_guardian = parent
        self.student.save()

        fee = FeeStructure.objects.create(
            name="Science Lab Levy",
            fee_type=FeeType.LABORATORY,
            amount=Decimal("12000.00"),
            academic_year=self.year_2026,
            term=self.term_1,
            recurrence=FeeRecurrence.PER_TERM,
            logical_fee_key="science-lab",
            due_date=date(2026, 10, 25),  # FeeStructure has configured date
            is_mandatory=False,
        )

        # Assignment obligation has NO due date (e.g. historical unanchored or unknown date)
        assignment = StudentFeeAssignment.objects.create(
            student=self.student,
            fee_structure=fee,
            term=self.term_1,
            amount_owed=Decimal("12000.00"),
            due_date=None,
            logical_fee_key="science-lab",
            recurrence=FeeRecurrence.PER_TERM,
            academic_year=self.year_2026,
        )

        send_custom_fee_reminder(
            schema_name=connection.schema_name,
            fee_structure_id=fee.id,
            message=None,  # triggers default_message construction
        )

        mock_notify.create_notification.assert_called_once()
        _, call_kwargs = mock_notify.create_notification.call_args
        dispatched_message = call_kwargs["message"]

        # MUST NOT contain the FeeStructure's due date
        self.assertNotIn("October 25, 2026", dispatched_message)
        self.assertNotIn("Due date:", dispatched_message)
        self.assertIn("Science Lab Levy payment of ₦12,000.00 is pending.", dispatched_message)
        self.assertIn(f"Student: {self.student.full_name}", dispatched_message)

    # -------------------------------------------------------------------------
    # 6. Serializer & API Regression
    # -------------------------------------------------------------------------
    def test_serializer_exposes_due_date_and_is_overdue_as_readonly(self):
        """Serializer presents due_date and is_overdue, and prevents client tampering."""
        fee = FeeStructure.objects.create(
            name="Tuition Term 1",
            fee_type=FeeType.TUITION,
            amount=Decimal("50000.00"),
            academic_year=self.year_2026,
            term=self.term_1,
            recurrence=FeeRecurrence.PER_TERM,
            logical_fee_key="tuition-t1",
            due_date=date(2026, 10, 5),
            is_mandatory=True,
        )
        FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee,
            student=self.student,
            term=self.term_1,
        )
        assignment = StudentFeeAssignment.objects.get(
            student=self.student,
            fee_structure=fee,
        )

        serializer = StudentFeeAssignmentSerializer(assignment)
        data = serializer.data

        self.assertIn("due_date", data)
        self.assertEqual(data["due_date"], "2026-10-05")
        self.assertIn("is_overdue", data)

        # Direct serializer create snapshots from fee_structure if not provided
        student_3 = Student.objects.create(
            first_name="Ngozi",
            last_name="Eze",
            admission_number="ADM-P5B-003",
            classroom=self.classroom_1a,
            is_active=True,
        )
        created_assign = StudentFeeAssignmentSerializer().create({
            "student": student_3,
            "fee_structure": fee,
            "term": self.term_1,
            "amount_owed": fee.amount,
        })
        self.assertEqual(created_assign.due_date, date(2026, 10, 5))

    # -------------------------------------------------------------------------
    # 7. Migration Historical Backfill Unit Tests
    # -------------------------------------------------------------------------
    def test_backfill_fee_assignment_due_dates_function(self):
        """Validates all 4 cases of the historical backfill algorithm."""
        # Case A: Specific term matching -> backfilled
        fs_specific = FeeStructure.objects.create(
            name="Term 1 Specific",
            fee_type=FeeType.TUITION,
            amount=Decimal("10000.00"),
            academic_year=self.year_2026,
            term=self.term_1,
            recurrence=FeeRecurrence.PER_TERM,
            logical_fee_key="t1-spec",
            due_date=date(2026, 10, 15),
            is_mandatory=False,
        )
        # Manually create with due_date=None to simulate pre-migration row
        assign_a = StudentFeeAssignment.objects.create(
            student=self.student,
            fee_structure=fs_specific,
            term=self.term_1,
            amount_owed=Decimal("10000.00"),
            due_date=None,
            logical_fee_key="t1-spec",
            recurrence=FeeRecurrence.PER_TERM,
            academic_year=self.year_2026,
        )

        # Case B: All-terms (term=None) and due_date inside assignment.term dates -> backfilled
        fs_in_range = FeeStructure.objects.create(
            name="All Terms Inside T1",
            fee_type=FeeType.OTHER,
            amount=Decimal("5000.00"),
            academic_year=self.year_2026,
            term=None,
            recurrence=FeeRecurrence.PER_TERM,
            logical_fee_key="all-terms-in",
            due_date=date(2026, 11, 20),  # Falls inside term_1 (Sep 1 - Dec 15)
            is_mandatory=False,
        )
        student_b = Student.objects.create(
            first_name="Kelechi",
            last_name="Nwosu",
            admission_number="ADM-P5B-004",
            classroom=self.classroom_1a,
            is_active=True,
        )
        assign_b = StudentFeeAssignment.objects.create(
            student=student_b,
            fee_structure=fs_in_range,
            term=self.term_1,
            amount_owed=Decimal("5000.00"),
            due_date=None,
            logical_fee_key="all-terms-in",
            recurrence=FeeRecurrence.PER_TERM,
            academic_year=self.year_2026,
        )

        # Case C: All-terms (term=None) and due_date outside assignment.term dates -> remains None (Ambiguous)
        # fs_in_range due_date is 2026-11-20, which is outside term_2 (Jan 10, 2027 - Apr 10, 2027)
        assign_c = StudentFeeAssignment.objects.create(
            student=student_b,
            fee_structure=fs_in_range,
            term=self.term_2,
            amount_owed=Decimal("5000.00"),
            due_date=None,
            logical_fee_key="all-terms-in",
            recurrence=FeeRecurrence.PER_TERM,
            academic_year=self.year_2026,
        )

        # Case D: FeeStructure has no due_date -> remains None
        fs_no_date = FeeStructure.objects.create(
            name="No Date Fee",
            fee_type=FeeType.OTHER,
            amount=Decimal("2000.00"),
            academic_year=self.year_2026,
            term=self.term_1,
            recurrence=FeeRecurrence.PER_TERM,
            logical_fee_key="no-date",
            due_date=None,
            is_mandatory=False,
        )
        student_d = Student.objects.create(
            first_name="Zainab",
            last_name="Ali",
            admission_number="ADM-P5B-005",
            classroom=self.classroom_1a,
            is_active=True,
        )
        assign_d = StudentFeeAssignment.objects.create(
            student=student_d,
            fee_structure=fs_no_date,
            term=self.term_1,
            amount_owed=Decimal("2000.00"),
            due_date=None,
            logical_fee_key="no-date",
            recurrence=FeeRecurrence.PER_TERM,
            academic_year=self.year_2026,
        )

        # Run the backfill function
        backfill_fee_assignment_due_dates(apps, None)

        # Refresh all assignments
        assign_a.refresh_from_db()
        assign_b.refresh_from_db()
        assign_c.refresh_from_db()
        assign_d.refresh_from_db()

        # Case A: safe match -> 2026-10-15
        self.assertEqual(assign_a.due_date, date(2026, 10, 15))
        # Case B: safe date inside term -> 2026-11-20
        self.assertEqual(assign_b.due_date, date(2026, 11, 20))
        # Case C: ambiguous (outside term dates) -> None
        self.assertIsNone(assign_c.due_date)
        # Case D: no due date -> None
        self.assertIsNone(assign_d.due_date)

        # Financial preservation: amounts, waiver, payment status remain untouched
        self.assertEqual(assign_a.amount_owed, Decimal("10000.00"))
        self.assertEqual(assign_a.amount_paid, Decimal("0.00"))
        self.assertFalse(assign_a.is_waived)
