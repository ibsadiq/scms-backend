from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from rest_framework import status
from rest_framework.test import APIClient
from school.testcases import TenantTestCase

from academic.models import ClassRoom, GradeLevel, Student, StudentClassEnrollment
from users.models import CustomUser
from administration.models import AcademicYear, Term
from finance.models import (
    FeeApplicability,
    FeeRecurrence,
    FeeStructure,
    FeeTermSchedule,
    FeeType,
    StudentFeeAssignment,
)
from finance.serializers import FeeStructureSerializer
from finance.services import FeeAssignmentService


class FeeTermSchedulePhase5CTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.status = "active"
        return super().setup_tenant(tenant)

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)

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

        self.term_3 = Term.objects.create(
            name="Third Term 2027",
            academic_year=self.year_2026,
            start_date=date(2027, 4, 25),
            end_date=date(2027, 7, 20),
        )

        self.term_other_year = Term.objects.create(
            name="First Term 2027/2028",
            academic_year=self.year_2027,
            start_date=date(2027, 9, 1),
            end_date=date(2027, 12, 15),
        )

        self.grade_1 = GradeLevel.objects.update_or_create(
            system_code="GRADE_1",
            defaults={"section": "PRIMARY", "default_name": "Grade 1", "sequence_order": 1},
        )[0]

        self.classroom_1 = ClassRoom.objects.create(
            name="Primary 1A",
            grade_level=self.grade_1,
            capacity=30,
        )

        self.student = Student.objects.create(
            first_name="Ada",
            last_name="Lovelace",
            admission_number="ADM-P5C-001",
            parent_contact="08011111111",
            is_active=True,
            classroom=self.classroom_1,
        )

        self.enrollment = StudentClassEnrollment.objects.create(
            student=self.student,
            classroom=self.classroom_1,
            academic_year=self.year_2026,
            is_active=True,
        )

        self.admin_user = CustomUser.objects.create_user(
            email="finance_admin_5c@test.com",
            password="testpassword123",
            is_staff=True,
            is_superuser=True,
            is_admin=True,
        )

        self.client = APIClient(HTTP_HOST=self.domain.domain)
        self.client.force_authenticate(user=self.admin_user)

    # =========================================================================
    # Model Validation Tests (1 - 8)
    # =========================================================================

    def test_01_valid_per_term_all_terms_schedule(self):
        """1. valid PER_TERM + All Terms schedule saves cleanly."""
        fee = FeeStructure.objects.create(
            name="Tuition 2026/2027",
            amount=Decimal("100000.00"),
            academic_year=self.year_2026,
            term=None,
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=False,
        )
        schedule = FeeTermSchedule(
            fee_structure=fee,
            term=self.term_1,
            amount=Decimal("95000.00"),
            due_date=date(2026, 10, 5),
        )
        schedule.full_clean()
        schedule.save()
        self.assertIsNotNone(schedule.pk)
        self.assertEqual(schedule.amount, Decimal("95000.00"))
        self.assertEqual(schedule.due_date, date(2026, 10, 5))

    def test_02_reject_annual_schedule(self):
        """2. reject ANNUAL schedule."""
        fee = FeeStructure.objects.create(
            name="Annual ICT Fee",
            amount=Decimal("20000.00"),
            academic_year=self.year_2026,
            term=None,
            logical_fee_key="annual-ict-fee",
            recurrence=FeeRecurrence.ANNUAL,
            is_mandatory=False,
        )
        schedule = FeeTermSchedule(
            fee_structure=fee,
            term=self.term_1,
            amount=Decimal("20000.00"),
            due_date=date(2026, 10, 5),
        )
        with self.assertRaises(ValidationError) as ctx:
            schedule.full_clean()
        self.assertIn("only allowed for PER_TERM", str(ctx.exception))

    def test_03_reject_onetime_schedule(self):
        """3. reject ONE_TIME schedule."""
        fee = FeeStructure.objects.create(
            name="Admission Fee",
            amount=Decimal("50000.00"),
            academic_year=self.year_2026,
            term=None,
            logical_fee_key="admission-fee",
            recurrence=FeeRecurrence.ONE_TIME,
            is_mandatory=False,
        )
        schedule = FeeTermSchedule(
            fee_structure=fee,
            term=self.term_1,
            due_date=date(2026, 10, 5),
        )
        with self.assertRaises(ValidationError) as ctx:
            schedule.full_clean()
        self.assertIn("only allowed for PER_TERM", str(ctx.exception))

    def test_04_reject_specific_term_parent_schedule(self):
        """4. reject specific-term parent schedule."""
        fee = FeeStructure.objects.create(
            name="Term 1 Tuition",
            amount=Decimal("100000.00"),
            academic_year=self.year_2026,
            term=self.term_1,
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=False,
        )
        schedule = FeeTermSchedule(
            fee_structure=fee,
            term=self.term_1,
            due_date=date(2026, 10, 5),
        )
        with self.assertRaises(ValidationError) as ctx:
            schedule.full_clean()
        self.assertIn("cannot be configured for specific-term", str(ctx.exception))

    def test_05_reject_term_from_another_academic_year(self):
        """5. reject term from another academic year."""
        fee = FeeStructure.objects.create(
            name="Tuition 2026/2027",
            amount=Decimal("100000.00"),
            academic_year=self.year_2026,
            term=None,
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=False,
        )
        schedule = FeeTermSchedule(
            fee_structure=fee,
            term=self.term_other_year,
            due_date=date(2027, 10, 5),
        )
        with self.assertRaises(ValidationError) as ctx:
            schedule.full_clean()
        self.assertIn("must belong to the fee structure's academic year", str(ctx.exception))

    def test_06_reject_due_date_outside_term(self):
        """6. reject due date outside term bounds."""
        fee = FeeStructure.objects.create(
            name="Tuition 2026/2027",
            amount=Decimal("100000.00"),
            academic_year=self.year_2026,
            term=None,
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=False,
        )
        # Term 1 is 2026-09-01 to 2026-12-15
        before_term = FeeTermSchedule(
            fee_structure=fee,
            term=self.term_1,
            due_date=date(2026, 8, 15),
        )
        with self.assertRaises(ValidationError) as ctx:
            before_term.full_clean()
        self.assertIn("Due date cannot be before term start date", str(ctx.exception))

        after_term = FeeTermSchedule(
            fee_structure=fee,
            term=self.term_1,
            due_date=date(2026, 12, 20),
        )
        with self.assertRaises(ValidationError) as ctx:
            after_term.full_clean()
        self.assertIn("Due date cannot be after term end date", str(ctx.exception))

    def test_07_reject_duplicate_fee_structure_term(self):
        """7. reject duplicate fee_structure + term."""
        fee = FeeStructure.objects.create(
            name="Tuition 2026/2027",
            amount=Decimal("100000.00"),
            academic_year=self.year_2026,
            term=None,
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=False,
        )
        FeeTermSchedule.objects.create(
            fee_structure=fee,
            term=self.term_1,
            due_date=date(2026, 10, 5),
        )
        with self.assertRaises(IntegrityError):
            FeeTermSchedule.objects.create(
                fee_structure=fee,
                term=self.term_1,
                due_date=date(2026, 11, 5),
            )

    def test_08_reject_invalid_amount_override(self):
        """8. reject invalid amount override (<= 0)."""
        fee = FeeStructure.objects.create(
            name="Tuition 2026/2027",
            amount=Decimal("100000.00"),
            academic_year=self.year_2026,
            term=None,
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=False,
        )
        schedule_zero = FeeTermSchedule(
            fee_structure=fee,
            term=self.term_1,
            amount=Decimal("0.00"),
            due_date=date(2026, 10, 5),
        )
        with self.assertRaises(ValidationError):
            schedule_zero.full_clean()

        schedule_neg = FeeTermSchedule(
            fee_structure=fee,
            term=self.term_1,
            amount=Decimal("-100.00"),
            due_date=date(2026, 10, 5),
        )
        with self.assertRaises(ValidationError):
            schedule_neg.full_clean()

    # =========================================================================
    # Resolution Tests (9 - 15)
    # =========================================================================

    def test_09_per_term_specific_term_resolves_feestructure_fields(self):
        """9. PER_TERM specific term resolves FeeStructure amount and due_date."""
        fee = FeeStructure.objects.create(
            name="First Term Tuition",
            amount=Decimal("85000.00"),
            academic_year=self.year_2026,
            term=self.term_1,
            due_date=date(2026, 10, 1),
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=False,
        )
        amount, due_date = FeeAssignmentService.resolve_assignment_financials(
            fee_structure=fee,
            target_term=self.term_1,
        )
        self.assertEqual(amount, Decimal("85000.00"))
        self.assertEqual(due_date, date(2026, 10, 1))

    def test_10_per_term_all_terms_resolves_matching_schedule(self):
        """10. PER_TERM All Terms resolves matching schedule."""
        fee = FeeStructure.objects.create(
            name="Tuition 2026/2027",
            amount=Decimal("100000.00"),
            academic_year=self.year_2026,
            term=None,
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=False,
        )
        FeeTermSchedule.objects.create(
            fee_structure=fee,
            term=self.term_1,
            amount=Decimal("95000.00"),
            due_date=date(2026, 10, 5),
        )
        amount, due_date = FeeAssignmentService.resolve_assignment_financials(
            fee_structure=fee,
            target_term=self.term_1,
        )
        self.assertEqual(amount, Decimal("95000.00"))
        self.assertEqual(due_date, date(2026, 10, 5))

    def test_11_nullable_schedule_amount_falls_back_to_feestructure_amount(self):
        """11. nullable schedule amount falls back to FeeStructure.amount."""
        fee = FeeStructure.objects.create(
            name="Tuition 2026/2027",
            amount=Decimal("100000.00"),
            academic_year=self.year_2026,
            term=None,
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=False,
        )
        FeeTermSchedule.objects.create(
            fee_structure=fee,
            term=self.term_2,
            amount=None,  # No override
            due_date=date(2027, 1, 25),
        )
        amount, due_date = FeeAssignmentService.resolve_assignment_financials(
            fee_structure=fee,
            target_term=self.term_2,
        )
        self.assertEqual(amount, Decimal("100000.00"))
        self.assertEqual(due_date, date(2027, 1, 25))

    def test_12_schedule_amount_override_is_used(self):
        """12. schedule amount override is used over base amount."""
        fee = FeeStructure.objects.create(
            name="Tuition 2026/2027",
            amount=Decimal("100000.00"),
            academic_year=self.year_2026,
            term=None,
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=False,
        )
        FeeTermSchedule.objects.create(
            fee_structure=fee,
            term=self.term_3,
            amount=Decimal("110000.00"),
            due_date=date(2027, 5, 10),
        )
        amount, due_date = FeeAssignmentService.resolve_assignment_financials(
            fee_structure=fee,
            target_term=self.term_3,
        )
        self.assertEqual(amount, Decimal("110000.00"))
        self.assertEqual(due_date, date(2027, 5, 10))

    def test_13_missing_schedule_raises_configuration_error(self):
        """13. missing schedule raises clear configuration error."""
        fee = FeeStructure.objects.create(
            name="Tuition 2026/2027",
            amount=Decimal("100000.00"),
            academic_year=self.year_2026,
            term=None,
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=False,
        )
        with self.assertRaises(ValidationError) as ctx:
            FeeAssignmentService.resolve_assignment_financials(
                fee_structure=fee,
                target_term=self.term_2,
            )
        self.assertIn('No fee term schedule is configured for "Second Term 2027"', str(ctx.exception))

    def test_14_annual_resolves_feestructure_fields(self):
        """14. ANNUAL resolves FeeStructure fields directly."""
        fee = FeeStructure.objects.create(
            name="Annual Maintenance",
            amount=Decimal("15000.00"),
            academic_year=self.year_2026,
            term=None,
            due_date=date(2026, 11, 1),
            logical_fee_key="annual-maintenance",
            recurrence=FeeRecurrence.ANNUAL,
            is_mandatory=False,
        )
        amount, due_date = FeeAssignmentService.resolve_assignment_financials(
            fee_structure=fee,
            target_term=self.term_1,
        )
        self.assertEqual(amount, Decimal("15000.00"))
        self.assertEqual(due_date, date(2026, 11, 1))

    def test_15_onetime_resolves_feestructure_fields(self):
        """15. ONE_TIME resolves FeeStructure fields directly."""
        fee = FeeStructure.objects.create(
            name="Admission Package",
            amount=Decimal("45000.00"),
            academic_year=self.year_2026,
            term=None,
            due_date=date(2026, 9, 15),
            logical_fee_key="admission-pkg",
            recurrence=FeeRecurrence.ONE_TIME,
            is_mandatory=False,
        )
        amount, due_date = FeeAssignmentService.resolve_assignment_financials(
            fee_structure=fee,
            target_term=self.term_1,
        )
        self.assertEqual(amount, Decimal("45000.00"))
        self.assertEqual(due_date, date(2026, 9, 15))

    # =========================================================================
    # Snapshot Immutability Tests (16 - 18)
    # =========================================================================

    def test_16_assignment_snapshots_schedule_amount_and_due_date(self):
        """16. assignment snapshots schedule amount and due_date."""
        fee = FeeStructure.objects.create(
            name="Tuition 2026/2027",
            amount=Decimal("100000.00"),
            academic_year=self.year_2026,
            term=None,
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=False,
        )
        FeeTermSchedule.objects.create(
            fee_structure=fee,
            term=self.term_1,
            amount=Decimal("92000.00"),
            due_date=date(2026, 10, 10),
        )
        created = FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee,
            student=self.student,
            term=self.term_1,
        )
        self.assertEqual(created, 1)

        assignment = StudentFeeAssignment.objects.get(
            student=self.student,
            fee_structure=fee,
            term=self.term_1,
        )
        self.assertEqual(assignment.amount_owed, Decimal("92000.00"))
        self.assertEqual(assignment.due_date, date(2026, 10, 10))

    def test_17_editing_schedule_later_does_not_change_existing_assignment(self):
        """17. editing schedule later does not change existing assignment."""
        fee = FeeStructure.objects.create(
            name="Tuition 2026/2027",
            amount=Decimal("100000.00"),
            academic_year=self.year_2026,
            term=None,
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=False,
        )
        schedule = FeeTermSchedule.objects.create(
            fee_structure=fee,
            term=self.term_1,
            amount=Decimal("92000.00"),
            due_date=date(2026, 10, 10),
        )
        FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee,
            student=self.student,
            term=self.term_1,
        )

        assignment = StudentFeeAssignment.objects.get(
            student=self.student,
            fee_structure=fee,
            term=self.term_1,
        )

        # Later modification to schedule
        schedule.amount = Decimal("99000.00")
        schedule.due_date = date(2026, 10, 20)
        schedule.save()

        # Existing assignment snapshot must be preserved
        assignment.refresh_from_db()
        self.assertEqual(assignment.amount_owed, Decimal("92000.00"))
        self.assertEqual(assignment.due_date, date(2026, 10, 10))

    def test_18_new_later_assignment_uses_updated_schedule_configuration(self):
        """18. new later assignment uses updated schedule configuration."""
        fee = FeeStructure.objects.create(
            name="Tuition 2026/2027",
            amount=Decimal("100000.00"),
            academic_year=self.year_2026,
            term=None,
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=False,
        )
        schedule = FeeTermSchedule.objects.create(
            fee_structure=fee,
            term=self.term_1,
            amount=Decimal("92000.00"),
            due_date=date(2026, 10, 10),
        )
        FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee,
            student=self.student,
            term=self.term_1,
        )

        # Update schedule before a second student is assigned
        schedule.amount = Decimal("98000.00")
        schedule.due_date = date(2026, 10, 25)
        schedule.save()

        student_2 = Student.objects.create(
            first_name="Charles",
            last_name="Babbage",
            admission_number="ADM-P5C-002",
            is_active=True,
            classroom=self.classroom_1,
        )
        StudentClassEnrollment.objects.create(
            student=student_2,
            classroom=self.classroom_1,
            academic_year=self.year_2026,
            is_active=True,
        )

        FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee,
            student=student_2,
            term=self.term_1,
        )

        assign_2 = StudentFeeAssignment.objects.get(
            student=student_2,
            fee_structure=fee,
            term=self.term_1,
        )
        self.assertEqual(assign_2.amount_owed, Decimal("98000.00"))
        self.assertEqual(assign_2.due_date, date(2026, 10, 25))

    # =========================================================================
    # API Serializer & View Tests (19 - 24)
    # =========================================================================

    def test_19_nested_create_succeeds(self):
        """19. nested create succeeds via API."""
        payload = {
            "name": "Senior Tuition 2026/2027",
            "fee_type": FeeType.TUITION,
            "recurrence": FeeRecurrence.PER_TERM,
            "academic_year": self.year_2026.pk,
            "term": None,
            "amount": "100000.00",
            "due_date": None,
            "term_schedules": [
                {
                    "term": self.term_1.pk,
                    "amount": None,
                    "due_date": "2026-10-05",
                },
                {
                    "term": self.term_2.pk,
                    "amount": "105000.00",
                    "due_date": "2027-01-25",
                },
            ],
        }
        response = self.client.post("/api/finance/fee-structures/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        fee_id = response.data["id"]

        fee = FeeStructure.objects.get(pk=fee_id)
        self.assertEqual(fee.term_schedules.count(), 2)
        sched_1 = fee.term_schedules.get(term=self.term_1)
        self.assertIsNone(sched_1.amount)
        self.assertEqual(sched_1.due_date, date(2026, 10, 5))

        sched_2 = fee.term_schedules.get(term=self.term_2)
        self.assertEqual(sched_2.amount, Decimal("105000.00"))
        self.assertEqual(sched_2.due_date, date(2027, 1, 25))

    def test_20_nested_read_returns_schedules(self):
        """20. nested read returns schedules ordered by term start date."""
        fee = FeeStructure.objects.create(
            name="Ordered Tuition",
            amount=Decimal("100000.00"),
            academic_year=self.year_2026,
            term=None,
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=False,
        )
        FeeTermSchedule.objects.create(
            fee_structure=fee,
            term=self.term_2,
            due_date=date(2027, 1, 20),
        )
        FeeTermSchedule.objects.create(
            fee_structure=fee,
            term=self.term_1,
            due_date=date(2026, 10, 20),
        )

        response = self.client.get(f"/api/finance/fee-structures/{fee.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        schedules = response.data.get("term_schedules", [])
        self.assertEqual(len(schedules), 2)
        # Ordered by term start date: term_1 then term_2
        self.assertEqual(schedules[0]["term"], self.term_1.pk)
        self.assertEqual(schedules[1]["term"], self.term_2.pk)

    def test_21_nested_update_modifies_future_config(self):
        """21. nested update modifies future config without altering historical assignments."""
        fee = FeeStructure.objects.create(
            name="Updatable Tuition",
            amount=Decimal("100000.00"),
            academic_year=self.year_2026,
            term=None,
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=False,
        )
        sched_1 = FeeTermSchedule.objects.create(
            fee_structure=fee,
            term=self.term_1,
            amount=Decimal("95000.00"),
            due_date=date(2026, 10, 10),
        )
        FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee,
            student=self.student,
            term=self.term_1,
        )
        past_assign = StudentFeeAssignment.objects.get(
            student=self.student, fee_structure=fee, term=self.term_1
        )

        # Update via API: modify term 1 schedule, add term 2 schedule
        update_payload = {
            "name": "Updatable Tuition",
            "amount": "100000.00",
            "academic_year": self.year_2026.pk,
            "recurrence": FeeRecurrence.PER_TERM,
            "term_schedules": [
                {
                    "term": self.term_1.pk,
                    "amount": "99000.00",
                    "due_date": "2026-10-15",
                },
                {
                    "term": self.term_2.pk,
                    "amount": "105000.00",
                    "due_date": "2027-02-01",
                },
            ],
        }
        response = self.client.put(
            f"/api/finance/fee-structures/{fee.pk}/",
            update_payload,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Past assignment must not be mutated
        past_assign.refresh_from_db()
        self.assertEqual(past_assign.amount_owed, Decimal("95000.00"))
        self.assertEqual(past_assign.due_date, date(2026, 10, 10))

        # Schedule must be updated
        sched_1.refresh_from_db()
        self.assertEqual(sched_1.amount, Decimal("99000.00"))
        self.assertEqual(sched_1.due_date, date(2026, 10, 15))
        self.assertTrue(fee.term_schedules.filter(term=self.term_2).exists())

    def test_22_schedule_validation_errors_returned_cleanly(self):
        """22. schedule validation errors returned cleanly via API."""
        payload = {
            "name": "Invalid Due Date Fee",
            "fee_type": FeeType.TUITION,
            "recurrence": FeeRecurrence.PER_TERM,
            "academic_year": self.year_2026.pk,
            "amount": "100000.00",
            "term_schedules": [
                {
                    "term": self.term_1.pk,
                    "amount": "95000.00",
                    "due_date": "2025-01-01",  # Outside term
                }
            ],
        }
        response = self.client.post("/api/finance/fee-structures/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        errors = response.data.get("detail", response.data)
        self.assertIn("term_schedules", errors)

    def test_23_duplicate_term_schedules_rejected(self):
        """23. duplicate term schedules in API payload rejected."""
        payload = {
            "name": "Duplicate Schedule Fee",
            "fee_type": FeeType.TUITION,
            "recurrence": FeeRecurrence.PER_TERM,
            "academic_year": self.year_2026.pk,
            "amount": "100000.00",
            "term_schedules": [
                {
                    "term": self.term_1.pk,
                    "due_date": "2026-10-05",
                },
                {
                    "term": self.term_1.pk,  # Duplicate
                    "due_date": "2026-11-05",
                },
            ],
        }
        response = self.client.post("/api/finance/fee-structures/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        errors = response.data.get("detail", response.data)
        self.assertIn("term_schedules", errors)
        self.assertIn("Duplicate schedule", str(errors["term_schedules"]))

    def test_24_invalid_cross_year_term_rejected(self):
        """24. invalid cross-year term in schedule rejected."""
        payload = {
            "name": "Cross Year Fee",
            "fee_type": FeeType.TUITION,
            "recurrence": FeeRecurrence.PER_TERM,
            "academic_year": self.year_2026.pk,
            "amount": "100000.00",
            "term_schedules": [
                {
                    "term": self.term_other_year.pk,  # 2027/2028 term for 2026/2027 fee
                    "due_date": "2027-10-05",
                }
            ],
        }
        response = self.client.post("/api/finance/fee-structures/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        errors = response.data.get("detail", response.data)
        self.assertIn("term_schedules", errors)
        self.assertIn("academic year", str(errors["term_schedules"]))

    # =========================================================================
    # Signal / Auto-Assignment Tests (25 - 27)
    # =========================================================================

    def test_25_mandatory_feestructure_with_nested_schedules_does_not_prematurely_assign(self):
        """25. mandatory FeeStructure with nested schedules does not fail or auto-assign before schedules exist."""
        # Using serializer create directly or API client
        payload = {
            "name": "Mandatory Scheduled Tuition",
            "fee_type": FeeType.TUITION,
            "recurrence": FeeRecurrence.PER_TERM,
            "academic_year": self.year_2026.pk,
            "amount": "120000.00",
            "is_mandatory": True,
            "term_schedules": [
                {
                    "term": self.term_1.pk,
                    "amount": "115000.00",
                    "due_date": "2026-10-05",
                }
            ],
        }
        # Must succeed without throwing ValidationError during post_save signal
        response = self.client.post("/api/finance/fee-structures/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_26_after_complete_creation_assignment_uses_schedule_values(self):
        """26. after complete creation, assignment uses schedule values."""
        serializer = FeeStructureSerializer(
            data={
                "name": "Complete Mandatory Tuition",
                "fee_type": FeeType.TUITION,
                "recurrence": FeeRecurrence.PER_TERM,
                "academic_year": self.year_2026.pk,
                "amount": "100000.00",
                "is_mandatory": True,
                "term_schedules": [
                    {
                        "term": self.term_1.pk,
                        "amount": "108000.00",
                        "due_date": "2026-10-12",
                    }
                ],
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        fee = serializer.save()

        # Execute assignment
        assigned_count = FeeAssignmentService.assign_fee(fee_structure=fee)
        self.assertGreaterEqual(assigned_count, 1)

        assignment = StudentFeeAssignment.objects.get(
            student=self.student,
            fee_structure=fee,
            term=self.term_1,
        )
        self.assertEqual(assignment.amount_owed, Decimal("108000.00"))
        self.assertEqual(assignment.due_date, date(2026, 10, 12))

    def test_27_existing_specific_term_mandatory_feestructure_auto_assignment_still_works(self):
        """27. existing specific-term mandatory FeeStructure auto-assignment still works."""
        fee = FeeStructure.objects.create(
            name="Specific Mandatory Term 1",
            fee_type=FeeType.TUITION,
            recurrence=FeeRecurrence.PER_TERM,
            academic_year=self.year_2026,
            term=self.term_1,
            amount=Decimal("75000.00"),
            due_date=date(2026, 10, 1),
            is_mandatory=True,
        )
        # Calling assign_fee on specific term fee
        assigned = FeeAssignmentService.assign_fee(fee_structure=fee)
        self.assertGreaterEqual(assigned, 1)

        assignment = StudentFeeAssignment.objects.get(
            student=self.student,
            fee_structure=fee,
            term=self.term_1,
        )
        self.assertEqual(assignment.amount_owed, Decimal("75000.00"))
        self.assertEqual(assignment.due_date, date(2026, 10, 1))

    # =========================================================================
    # Regression Tests (28 - 32)
    # =========================================================================

    def test_28_one_time_new_students_only_still_assigns_only_genuine_new_students(self):
        """28. ONE_TIME + NEW_STUDENTS_ONLY still assigns only genuine new students."""
        # Ada has an enrollment in 2026/2027. Create student_ret with prior enrollment in 2025
        year_2025 = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            active_year=False,
        )
        student_ret = Student.objects.create(
            first_name="Returning",
            last_name="Student",
            admission_number="ADM-RET-001",
            is_active=True,
            classroom=self.classroom_1,
        )
        StudentClassEnrollment.objects.create(
            student=student_ret,
            classroom=self.classroom_1,
            academic_year=year_2025,
            is_active=False,
        )
        StudentClassEnrollment.objects.create(
            student=student_ret,
            classroom=self.classroom_1,
            academic_year=self.year_2026,
            is_active=True,
        )

        admission_fee = FeeStructure.objects.create(
            name="Admission Fee 2026",
            amount=Decimal("50000.00"),
            academic_year=self.year_2026,
            term=None,
            due_date=date(2026, 9, 15),
            logical_fee_key="admission-fee",
            recurrence=FeeRecurrence.ONE_TIME,
            applicability=FeeApplicability.NEW_STUDENTS_ONLY,
            is_mandatory=True,
        )

        # Ada is new to 2026/2027 (no prior enrollment before 2026)
        self.assertTrue(admission_fee.applies_to_student(self.student, self.term_1))
        # Returning student is not new
        self.assertFalse(admission_fee.applies_to_student(student_ret, self.term_1))

        # Assign fee
        c1 = FeeAssignmentService.assign_fee_to_student(
            fee_structure=admission_fee, student=self.student, term=self.term_1
        )
        c2 = FeeAssignmentService.assign_fee_to_student(
            fee_structure=admission_fee, student=student_ret, term=self.term_1
        )
        self.assertEqual(c1, 1)
        self.assertEqual(c2, 0)

    def test_29_one_time_idempotency_still_holds(self):
        """29. ONE_TIME idempotency still holds across terms and academic years."""
        onetime_fee = FeeStructure.objects.create(
            name="Registration Fee",
            amount=Decimal("25000.00"),
            academic_year=self.year_2026,
            term=None,
            due_date=date(2026, 9, 20),
            logical_fee_key="registration-fee",
            recurrence=FeeRecurrence.ONE_TIME,
            is_mandatory=True,
        )
        c1 = FeeAssignmentService.assign_fee_to_student(
            fee_structure=onetime_fee, student=self.student, term=self.term_1
        )
        self.assertEqual(c1, 1)

        # Repeated assignment in same term returns 0
        c2 = FeeAssignmentService.assign_fee_to_student(
            fee_structure=onetime_fee, student=self.student, term=self.term_1
        )
        self.assertEqual(c2, 0)

        # Assignment in later term returns 0
        c3 = FeeAssignmentService.assign_fee_to_student(
            fee_structure=onetime_fee, student=self.student, term=self.term_2
        )
        self.assertEqual(c3, 0)

    def test_30_annual_idempotency_still_holds(self):
        """30. ANNUAL idempotency still holds across terms within academic year."""
        annual_fee = FeeStructure.objects.create(
            name="Annual Development Levy",
            amount=Decimal("30000.00"),
            academic_year=self.year_2026,
            term=None,
            due_date=date(2026, 10, 1),
            logical_fee_key="annual-dev-levy",
            recurrence=FeeRecurrence.ANNUAL,
            is_mandatory=True,
        )
        c1 = FeeAssignmentService.assign_fee_to_student(
            fee_structure=annual_fee, student=self.student, term=self.term_1
        )
        self.assertEqual(c1, 1)

        # In Term 2, cannot be assigned again for same academic year
        c2 = FeeAssignmentService.assign_fee_to_student(
            fee_structure=annual_fee, student=self.student, term=self.term_2
        )
        self.assertEqual(c2, 0)

    def test_31_sync_enrollment_fees_still_works(self):
        """31. sync_fees_for_enrollment still works with scheduled and non-scheduled fees."""
        # 1. Scheduled PER_TERM fee
        sched_fee = FeeStructure.objects.create(
            name="Tuition Fee",
            amount=Decimal("100000.00"),
            academic_year=self.year_2026,
            term=None,
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=True,
        )
        FeeTermSchedule.objects.create(
            fee_structure=sched_fee,
            term=self.term_1,
            amount=Decimal("95000.00"),
            due_date=date(2026, 10, 5),
        )

        # 2. Specific term fee
        spec_fee = FeeStructure.objects.create(
            name="Term 1 Lab Fee",
            amount=Decimal("10000.00"),
            academic_year=self.year_2026,
            term=self.term_1,
            due_date=date(2026, 10, 10),
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=True,
        )

        res = FeeAssignmentService.sync_fees_for_enrollment(
            enrollment=self.enrollment,
            term=self.term_1,
            return_details=True,
        )
        self.assertEqual(res["created_count"], 2)
        self.assertEqual(res["existing_count"], 0)

        assign_sched = StudentFeeAssignment.objects.get(
            student=self.student, fee_structure=sched_fee, term=self.term_1
        )
        self.assertEqual(assign_sched.amount_owed, Decimal("95000.00"))
        self.assertEqual(assign_sched.due_date, date(2026, 10, 5))

        assign_spec = StudentFeeAssignment.objects.get(
            student=self.student, fee_structure=spec_fee, term=self.term_1
        )
        self.assertEqual(assign_spec.amount_owed, Decimal("10000.00"))
        self.assertEqual(assign_spec.due_date, date(2026, 10, 10))

    def test_32_phase5b_due_date_snapshot_behavior_remains_intact(self):
        """32. Phase 5B due-date snapshot behavior remains intact."""
        fee = FeeStructure.objects.create(
            name="Term Fee Phase 5B",
            amount=Decimal("50000.00"),
            academic_year=self.year_2026,
            term=self.term_1,
            due_date=date(2026, 10, 15),
            recurrence=FeeRecurrence.PER_TERM,
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
            term=self.term_1,
        )
        self.assertEqual(assignment.due_date, date(2026, 10, 15))

        # Modifying FeeStructure due date later does NOT change historical assignment due_date
        fee.due_date = date(2026, 11, 20)
        fee.save()

        assignment.refresh_from_db()
        self.assertEqual(assignment.due_date, date(2026, 10, 15))

    # =========================================================================
    # Phase 5C Hardening & Regression Tests (33 - 37)
    # =========================================================================

    def test_33_sync_fees_for_enrollment_does_not_silently_skip_missing_schedule(self):
        """33. sync_fees_for_enrollment does not silently skip unscheduled target terms."""
        fee = FeeStructure.objects.create(
            name="Unscheduled Tuition",
            amount=Decimal("80000.00"),
            academic_year=self.year_2026,
            term=None,
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=True,
        )
        # Configure schedule for Term 1 only
        FeeTermSchedule.objects.create(
            fee_structure=fee,
            term=self.term_1,
            due_date=date(2026, 10, 5),
        )

        # Syncing for Term 2 (no schedule configured) with return_details=True
        res = FeeAssignmentService.sync_fees_for_enrollment(
            enrollment=self.enrollment,
            term=self.term_2,
            return_details=True,
        )
        # Invariant: fee must be counted as applicable, not silently dropped
        self.assertEqual(res["applicable_count"], 1)
        self.assertEqual(res["created_count"], 0)
        self.assertEqual(res["would_create_count"], 0)
        self.assertGreaterEqual(len(res["errors"]), 1)
        self.assertIn('No fee term schedule is configured for "Second Term 2027"', res["errors"][0])

        # Calling sync_fees_for_enrollment without return_details=True must raise ValidationError
        with self.assertRaises(ValidationError) as ctx:
            FeeAssignmentService.sync_fees_for_enrollment(
                enrollment=self.enrollment,
                term=self.term_2,
                return_details=False,
            )
        self.assertIn('No fee term schedule is configured for "Second Term 2027"', str(ctx.exception))

        # No assignment was created
        self.assertFalse(
            StudentFeeAssignment.objects.filter(
                student=self.student,
                fee_structure=fee,
                term=self.term_2,
            ).exists()
        )

    def test_34_nested_update_absent_term_schedules_preserves_existing_schedules(self):
        """34. update without term_schedules key preserves all existing schedules."""
        fee = FeeStructure.objects.create(
            name="Original Fee Name",
            amount=Decimal("100000.00"),
            academic_year=self.year_2026,
            term=None,
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=False,
        )
        sched_1 = FeeTermSchedule.objects.create(
            fee_structure=fee,
            term=self.term_1,
            amount=Decimal("95000.00"),
            due_date=date(2026, 10, 5),
        )
        sched_2 = FeeTermSchedule.objects.create(
            fee_structure=fee,
            term=self.term_2,
            amount=Decimal("105000.00"),
            due_date=date(2027, 1, 20),
        )

        # PATCH/PUT without 'term_schedules' key
        payload = {
            "name": "Updated Fee Name",
            "amount": "102000.00",
        }
        response = self.client.patch(
            f"/api/finance/fee-structures/{fee.pk}/",
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        fee.refresh_from_db()
        self.assertEqual(fee.name, "Updated Fee Name")
        self.assertEqual(fee.amount, Decimal("102000.00"))

        # Both schedules must remain completely intact
        self.assertEqual(fee.term_schedules.count(), 2)
        sched_1.refresh_from_db()
        self.assertEqual(sched_1.amount, Decimal("95000.00"))
        self.assertEqual(sched_1.due_date, date(2026, 10, 5))
        sched_2.refresh_from_db()
        self.assertEqual(sched_2.amount, Decimal("105000.00"))
        self.assertEqual(sched_2.due_date, date(2027, 1, 20))

    def test_35_nested_update_explicit_term_schedules_replaces_and_upserts(self):
        """35. explicit term_schedules payload updates, inserts, and removes as expected."""
        fee = FeeStructure.objects.create(
            name="Upsert Fee",
            amount=Decimal("100000.00"),
            academic_year=self.year_2026,
            term=None,
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=False,
        )
        sched_1 = FeeTermSchedule.objects.create(
            fee_structure=fee,
            term=self.term_1,
            amount=Decimal("90000.00"),
            due_date=date(2026, 10, 5),
        )
        FeeTermSchedule.objects.create(
            fee_structure=fee,
            term=self.term_2,
            amount=Decimal("100000.00"),
            due_date=date(2027, 1, 20),
        )

        # Update: update Term 1, omit Term 2 (to delete it), add Term 3
        payload = {
            "term_schedules": [
                {
                    "term": self.term_1.pk,
                    "amount": "92000.00",
                    "due_date": "2026-10-15",
                },
                {
                    "term": self.term_3.pk,
                    "amount": "110000.00",
                    "due_date": "2027-05-10",
                },
            ]
        }
        response = self.client.patch(
            f"/api/finance/fee-structures/{fee.pk}/",
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(fee.term_schedules.count(), 2)
        # Term 1 updated in place
        sched_1.refresh_from_db()
        self.assertEqual(sched_1.amount, Decimal("92000.00"))
        self.assertEqual(sched_1.due_date, date(2026, 10, 15))
        # Term 2 deleted
        self.assertFalse(fee.term_schedules.filter(term=self.term_2).exists())
        # Term 3 created
        self.assertTrue(fee.term_schedules.filter(term=self.term_3).exists())

    def test_36_nested_update_explicit_empty_term_schedules_removes_all_schedules(self):
        """36. explicit empty term_schedules list safely removes all schedules."""
        fee = FeeStructure.objects.create(
            name="Clear Schedules Fee",
            amount=Decimal("100000.00"),
            academic_year=self.year_2026,
            term=None,
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=False,
        )
        FeeTermSchedule.objects.create(
            fee_structure=fee,
            term=self.term_1,
            due_date=date(2026, 10, 5),
        )
        self.assertEqual(fee.term_schedules.count(), 1)

        payload = {"term_schedules": []}
        response = self.client.patch(
            f"/api/finance/fee-structures/{fee.pk}/",
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(fee.term_schedules.count(), 0)

    def test_37_invalid_nested_create_rolls_back_and_defers_no_auto_assignment(self):
        """37. invalid nested create rolls back completely and deferred auto-assignment does not run."""
        payload = {
            "name": "Failing Mandatory Fee",
            "fee_type": FeeType.TUITION,
            "recurrence": FeeRecurrence.PER_TERM,
            "academic_year": self.year_2026.pk,
            "amount": "100000.00",
            "is_mandatory": True,
            "term_schedules": [
                {
                    "term": self.term_1.pk,
                    "amount": "95000.00",
                    "due_date": "2025-01-01",  # Invalid date outside Term 1 bounds
                }
            ],
        }
        response = self.client.post("/api/finance/fee-structures/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Atomic rollback verification:
        # FeeStructure must NOT exist in DB
        self.assertFalse(FeeStructure.objects.filter(name="Failing Mandatory Fee").exists())
        # FeeTermSchedule must NOT exist in DB
        self.assertFalse(FeeTermSchedule.objects.filter(due_date=date(2025, 1, 1)).exists())
        # Deferred auto-assignment must NOT have run (0 assignments for this student)
        self.assertEqual(
            StudentFeeAssignment.objects.filter(
                student=self.student,
                fee_structure__name="Failing Mandatory Fee",
            ).count(),
            0,
        )

