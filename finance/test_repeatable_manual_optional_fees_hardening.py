from datetime import date
from decimal import Decimal
import threading

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection, transaction, IntegrityError, models
from rest_framework import status
from rest_framework.test import APIClient
from school.testcases import TenantTestCase, TenantTransactionTestCase

from academic.models import (
    ClassRoom,
    Department,
    GradeLevel,
    Parent,
    SectionType,
    Student,
    StudentClassEnrollment,
    Subject,
    Teacher,
)
from administration.models import AcademicYear, Term
from finance.models import (
    FeeAdjustment,
    FeePaymentAllocation,
    FeeRecurrence,
    FeeStructure,
    FeeTermSchedule,
    FeeType,
    OptionalService,
    Receipt,
    ServiceSubscription,
    StudentFeeAssignment,
)
from finance.serializers import StudentFeeAssignmentSerializer
from finance.services.fee_assignment_service import FeeAssignmentService
from finance.services.payment_allocation_service import PaymentAllocationService

User = get_user_model()


class BaseHardeningSetupMixin:
    """Shared fixture setup for repeatable manual optional fees hardening tests."""

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.status = "active"
        return super().setup_tenant(tenant)

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)

        self.accountant = User.objects.create_user(
            email="hardening-accountant@test.local",
            password="testpassword",
            is_staff=True,
            is_superuser=True,
            is_accountant=True,
            first_name="Finance",
            last_name="Accountant",
        )
        self.client = APIClient(HTTP_HOST=self.domain.domain)
        self.client.force_authenticate(user=self.accountant)

        self.year_1 = AcademicYear.objects.create(
            name="2028/2029",
            start_date=date(2028, 9, 1),
            end_date=date(2029, 7, 1),
            active_year=True,
        )
        self.year_2 = AcademicYear.objects.create(
            name="2029/2030",
            start_date=date(2029, 9, 1),
            end_date=date(2030, 7, 1),
            active_year=False,
        )
        self.term_yr2 = Term.objects.create(
            name="First Term 29/30",
            academic_year=self.year_2,
            start_date=date(2029, 9, 1),
            end_date=date(2029, 12, 1),
        )

        self.term_1 = Term.objects.create(
            name="First Term 28/29",
            academic_year=self.year_1,
            start_date=date(2028, 9, 1),
            end_date=date(2028, 12, 1),
        )
        self.term_2 = Term.objects.create(
            name="Second Term 28/29",
            academic_year=self.year_1,
            start_date=date(2029, 1, 10),
            end_date=date(2029, 4, 10),
        )

        self.grade_jss1 = GradeLevel.objects.create(
            system_code="JSS_1", section="JSS", default_name="JSS 1", sequence_order=1
        )
        self.classroom = ClassRoom.objects.create(
            name="JSS 1A", grade_level=self.grade_jss1, capacity=35
        )

        self.student_a = Student.objects.create(
            first_name="Amina",
            last_name="Bello",
            admission_number="GVA/JSS/28/0201",
            classroom=self.classroom,
            parent_contact="08011112222",
            is_active=True,
        )
        self.enrollment_a = StudentClassEnrollment.objects.create(
            student=self.student_a,
            classroom=self.classroom,
            academic_year=self.year_1,
            is_active=True,
        )

        self.student_b = Student.objects.create(
            first_name="Bashir",
            last_name="Danjuma",
            admission_number="GVA/JSS/28/0202",
            classroom=self.classroom,
            parent_contact="08033334444",
            is_active=True,
        )
        self.enrollment_b = StudentClassEnrollment.objects.create(
            student=self.student_b,
            classroom=self.classroom,
            academic_year=self.year_1,
            is_active=True,
        )

        # Optional Fee: School Uniform (ONE_TIME, is_mandatory=False)
        self.fee_uniform = FeeStructure.objects.create(
            name="School Uniform",
            amount=Decimal("15000.00"),
            fee_type=FeeType.OTHER,
            recurrence=FeeRecurrence.ONE_TIME,
            logical_fee_key="school-uniform",
            academic_year=self.year_1,
            term=self.term_1,
            is_mandatory=False,
            due_date=None,
            created_by=self.accountant,
        )

        # Mandatory Annual Fee: Development Levy (ANNUAL, is_mandatory=True)
        self.fee_dev_levy = FeeStructure.objects.create(
            name="Development Levy",
            amount=Decimal("30000.00"),
            fee_type=FeeType.MAINTENANCE,
            recurrence=FeeRecurrence.ANNUAL,
            logical_fee_key="dev-levy",
            academic_year=self.year_1,
            term=None,
            is_mandatory=True,
            created_by=self.accountant,
        )

        # Mandatory One-Time Fee: Admission Fee (ONE_TIME, is_mandatory=True)
        self.fee_admission = FeeStructure.objects.create(
            name="Admission Fee",
            amount=Decimal("50000.00"),
            fee_type=FeeType.ADMISSION,
            recurrence=FeeRecurrence.ONE_TIME,
            logical_fee_key="admission-fee",
            academic_year=self.year_1,
            term=None,
            is_mandatory=True,
            created_by=self.accountant,
        )

        # Mandatory Per-Term Fee: Tuition (PER_TERM, is_mandatory=True)
        self.fee_tuition = FeeStructure.objects.create(
            name="Tuition",
            amount=Decimal("100000.00"),
            fee_type=FeeType.TUITION,
            recurrence=FeeRecurrence.PER_TERM,
            logical_fee_key="tuition-fee",
            academic_year=self.year_1,
            term=self.term_1,
            is_mandatory=True,
            created_by=self.accountant,
        )


class DatabaseProtectionDirectORMTests(BaseHardeningSetupMixin, TenantTestCase):
    """
    Direct ORM adversarial tests establishing what PostgreSQL database constraints
    guarantee vs what is enforced at the service/model boundary.
    """

    def test_mandatory_onetime_duplicate_charge_1_blocked_by_db_constraint(self):
        """Database constraint blocks direct ORM duplicate charge_number=1 for ONE_TIME fee."""
        StudentFeeAssignment.objects.create(
            student=self.student_a,
            fee_structure=self.fee_admission,
            term=self.term_1,
            amount_owed=Decimal("50000.00"),
            amount_paid=Decimal("0.00"),
            logical_fee_key=self.fee_admission.logical_fee_key,
            recurrence=FeeRecurrence.ONE_TIME,
            academic_year=self.year_1,
            charge_number=1,
        )

        # Attempting direct ORM insert with same (student, logical_fee_key, charge_number=1)
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                StudentFeeAssignment.objects.create(
                    student=self.student_a,
                    fee_structure=self.fee_admission,
                    term=self.term_2,
                    amount_owed=Decimal("50000.00"),
                    amount_paid=Decimal("0.00"),
                    logical_fee_key=self.fee_admission.logical_fee_key,
                    recurrence=FeeRecurrence.ONE_TIME,
                    academic_year=self.year_1,
                    charge_number=1,
                )

    def test_mandatory_onetime_direct_orm_charge_2_is_service_boundary(self):
        """
        Direct ORM write with explicit charge_number=2 bypasses DB partial constraint
        (student, logical_fee_key, charge_number) because charge_number differs.
        Protection is strictly enforced at FeeAssignmentService and model.clean().
        """
        StudentFeeAssignment.objects.create(
            student=self.student_a,
            fee_structure=self.fee_admission,
            term=self.term_1,
            amount_owed=Decimal("50000.00"),
            amount_paid=Decimal("0.00"),
            logical_fee_key=self.fee_admission.logical_fee_key,
            recurrence=FeeRecurrence.ONE_TIME,
            academic_year=self.year_1,
            charge_number=1,
        )

        # FeeAssignmentService strictly blocks repeat on mandatory fee
        with self.assertRaises(ValidationError) as ctx:
            FeeAssignmentService.assign_fee_to_student(
                student=self.student_a,
                fee_structure=self.fee_admission,
                term=self.term_1,
                allow_repeat=True,
            )
        self.assertIn("Cannot repeat mandatory fee", str(ctx.exception))

    def test_mandatory_annual_duplicate_charge_1_blocked_by_db_constraint(self):
        """Database constraint blocks direct ORM duplicate charge_number=1 for ANNUAL fee in same academic year."""
        StudentFeeAssignment.objects.create(
            student=self.student_a,
            fee_structure=self.fee_dev_levy,
            term=self.term_1,
            amount_owed=Decimal("30000.00"),
            amount_paid=Decimal("0.00"),
            logical_fee_key=self.fee_dev_levy.logical_fee_key,
            recurrence=FeeRecurrence.ANNUAL,
            academic_year=self.year_1,
            charge_number=1,
        )

        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                StudentFeeAssignment.objects.create(
                    student=self.student_a,
                    fee_structure=self.fee_dev_levy,
                    term=self.term_2,
                    amount_owed=Decimal("30000.00"),
                    amount_paid=Decimal("0.00"),
                    logical_fee_key=self.fee_dev_levy.logical_fee_key,
                    recurrence=FeeRecurrence.ANNUAL,
                    academic_year=self.year_1,
                    charge_number=1,
                )

    def test_mandatory_per_term_duplicate_charge_1_blocked_by_db_constraint(self):
        """Database constraint blocks direct ORM duplicate charge_number=1 for PER_TERM fee in same term."""
        StudentFeeAssignment.objects.create(
            student=self.student_a,
            fee_structure=self.fee_tuition,
            term=self.term_1,
            amount_owed=Decimal("100000.00"),
            amount_paid=Decimal("0.00"),
            logical_fee_key=self.fee_tuition.logical_fee_key,
            recurrence=FeeRecurrence.PER_TERM,
            academic_year=self.year_1,
            charge_number=1,
        )

        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                StudentFeeAssignment.objects.create(
                    student=self.student_a,
                    fee_structure=self.fee_tuition,
                    term=self.term_1,
                    amount_owed=Decimal("100000.00"),
                    amount_paid=Decimal("0.00"),
                    logical_fee_key=self.fee_tuition.logical_fee_key,
                    recurrence=FeeRecurrence.PER_TERM,
                    academic_year=self.year_1,
                    charge_number=1,
                )


class ModelValidationTests(BaseHardeningSetupMixin, TenantTestCase):
    """Tests for model clean() validation and database CheckConstraints."""

    def test_full_clean_rejects_mandatory_fee_with_charge_number_greater_than_1(self):
        """StudentFeeAssignment.clean() rejects mandatory fee with charge_number > 1."""
        assignment = StudentFeeAssignment(
            student=self.student_a,
            fee_structure=self.fee_admission,
            term=self.term_1,
            amount_owed=Decimal("50000.00"),
            amount_paid=Decimal("0.00"),
            logical_fee_key="admission-fee",
            recurrence=FeeRecurrence.ONE_TIME,
            academic_year=self.year_1,
            charge_number=2,
        )
        with self.assertRaises(ValidationError) as ctx:
            assignment.full_clean()
        self.assertIn("Mandatory fees cannot have a charge number other than 1", str(ctx.exception))

    def test_full_clean_rejects_charge_number_less_than_1(self):
        """StudentFeeAssignment.clean() rejects charge_number < 1."""
        assignment = StudentFeeAssignment(
            student=self.student_a,
            fee_structure=self.fee_uniform,
            term=self.term_1,
            amount_owed=Decimal("15000.00"),
            amount_paid=Decimal("0.00"),
            logical_fee_key="school-uniform",
            recurrence=FeeRecurrence.ONE_TIME,
            academic_year=self.year_1,
            charge_number=0,
        )
        with self.assertRaises(ValidationError) as ctx:
            assignment.full_clean()
        self.assertIn("Charge number must be a positive integer", str(ctx.exception))

    def test_db_check_constraint_rejects_charge_number_zero(self):
        """PostgreSQL CheckConstraint finance_assignment_charge_number_positive rejects charge_number=0."""
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                StudentFeeAssignment.objects.create(
                    student=self.student_a,
                    fee_structure=self.fee_uniform,
                    term=self.term_1,
                    amount_owed=Decimal("15000.00"),
                    amount_paid=Decimal("0.00"),
                    logical_fee_key="school-uniform",
                    recurrence=FeeRecurrence.ONE_TIME,
                    academic_year=self.year_1,
                    charge_number=0,
                )


class ConcurrencyHardeningTests(BaseHardeningSetupMixin, TenantTransactionTestCase):
    """
    Dedicated multi-thread concurrency regression suite using TenantTransactionTestCase
    and close_old_connections() to prevent database deadlocks and test runner hangs.
    """

    def run_concurrent_workers(self, worker_fns):
        barrier = threading.Barrier(len(worker_fns))
        results = []
        errors = []

        def runner(fn):
            close_old_connections()
            try:
                connection.set_tenant(self.tenant)
                barrier.wait(timeout=10)
                results.append(fn())
            except Exception as exc:
                errors.append(exc)
            finally:
                close_old_connections()

        threads = [threading.Thread(target=runner, args=(fn,)) for fn in worker_fns]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        self.assertTrue(
            all(not t.is_alive() for t in threads),
            "Worker thread timed out; potential database lock deadlock.",
        )
        return results, errors

    def test_concurrent_first_assignments(self):
        """
        Two simultaneous manual assignment requests for a student with no prior assignment
        must both complete cleanly without uncaught IntegrityError or transaction poisoning.
        """
        student_id = self.student_a.id
        fee_id = self.fee_uniform.id
        term_id = self.term_1.id

        def worker():
            student = Student.objects.get(pk=student_id)
            fee = FeeStructure.objects.get(pk=fee_id)
            term = Term.objects.get(pk=term_id)
            return FeeAssignmentService.assign_fee_to_student(
                student=student,
                fee_structure=fee,
                term=term,
                allow_repeat=False,
            ).charge_number

        results, errors = self.run_concurrent_workers([worker, worker])
        self.assertEqual(errors, [], f"Unexpected concurrency errors: {errors}")
        self.assertEqual(results, [1, 1])

        # Exactly 1 row must exist
        charges = list(
            StudentFeeAssignment.objects.filter(
                student=self.student_a, fee_structure=self.fee_uniform
            ).values_list("charge_number", flat=True)
        )
        self.assertEqual(charges, [1])

    def test_concurrent_repeat_assignments(self):
        """
        Starting with charge_number=1, two simultaneous explicit repeat assignments
        serialize cleanly and produce charges 2 and 3 without duplicating charge_number.
        """
        # Initial charge #1
        FeeAssignmentService.assign_fee_to_student(
            student=self.student_a,
            fee_structure=self.fee_uniform,
            term=self.term_1,
            allow_repeat=False,
        )

        student_id = self.student_a.id
        fee_id = self.fee_uniform.id
        term_id = self.term_1.id

        def worker():
            student = Student.objects.get(pk=student_id)
            fee = FeeStructure.objects.get(pk=fee_id)
            term = Term.objects.get(pk=term_id)
            assignment = FeeAssignmentService.assign_fee_to_student(
                student=student,
                fee_structure=fee,
                term=term,
                allow_repeat=True,
            )
            return assignment.charge_number

        results, errors = self.run_concurrent_workers([worker, worker])
        self.assertEqual(errors, [], f"Unexpected concurrency errors: {errors}")
        self.assertEqual(len(results), 2)
        self.assertEqual(set(results), {2, 3})

        all_charges = list(
            StudentFeeAssignment.objects.filter(
                student=self.student_a, fee_structure=self.fee_uniform
            ).values_list("charge_number", flat=True).order_by("charge_number")
        )
        self.assertEqual(all_charges, [1, 2, 3])

    def test_concurrent_different_students_do_not_block_each_other(self):
        """Repeat assignment for Student A and Student B lock separate rows and execute concurrently."""
        FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )
        FeeAssignmentService.assign_fee_to_student(
            student=self.student_b, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )

        def worker_a():
            student = Student.objects.get(pk=self.student_a.id)
            fee = FeeStructure.objects.get(pk=self.fee_uniform.id)
            term = Term.objects.get(pk=self.term_1.id)
            return FeeAssignmentService.assign_fee_to_student(
                student=student, fee_structure=fee, term=term, allow_repeat=True
            ).charge_number

        def worker_b():
            student = Student.objects.get(pk=self.student_b.id)
            fee = FeeStructure.objects.get(pk=self.fee_uniform.id)
            term = Term.objects.get(pk=self.term_1.id)
            return FeeAssignmentService.assign_fee_to_student(
                student=student, fee_structure=fee, term=term, allow_repeat=True
            ).charge_number

        results, errors = self.run_concurrent_workers([worker_a, worker_b])
        self.assertEqual(errors, [], f"Unexpected errors: {errors}")
        self.assertEqual(results, [2, 2])


class SerializerAndApiBypassTests(BaseHardeningSetupMixin, TenantTestCase):
    """Tests auditing direct serializer creation and bulk_assign input parsing."""

    def test_direct_serializer_create_with_forged_charge_number_ignored(self):
        """Clients submitting arbitrary charge_number (e.g., 999) cannot forge charge sequence."""
        serializer = StudentFeeAssignmentSerializer(
            data={
                "student": self.student_a.id,
                "fee_structure": self.fee_uniform.id,
                "term": self.term_1.id,
                "charge_number": 999,
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        assign = serializer.save()
        # charge_number is read-only; server-assigned as 1
        self.assertEqual(assign.charge_number, 1)

    def test_allow_repeat_string_false_is_not_truthy(self):
        """bulk_assign with string 'false' must NOT enable repeat mode via Python truthiness."""
        # Initial assign
        res1 = self.client.post(
            "/api/finance/student-fee-assignments/bulk_assign/",
            {
                "fee_structure": self.fee_uniform.id,
                "term": self.term_1.id,
                "student_ids": [self.student_a.id],
                "allow_repeat": False,
            },
            format="json",
        )
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.assertEqual(res1.data["assigned_count"], 1)

        # Re-assign with string "false"
        res2 = self.client.post(
            "/api/finance/student-fee-assignments/bulk_assign/",
            {
                "fee_structure": self.fee_uniform.id,
                "term": self.term_1.id,
                "student_ids": [self.student_a.id],
                "allow_repeat": "false",
            },
            format="json",
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.data["assigned_count"], 0)
        self.assertEqual(res2.data["skipped_count"], 1)
        self.assertIn("already assigned", res2.data["skipped"][0]["reason"])

    def test_allow_repeat_string_true_enables_repeat(self):
        """bulk_assign with string 'true' enables repeat mode."""
        FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )

        res = self.client.post(
            "/api/finance/student-fee-assignments/bulk_assign/",
            {
                "fee_structure": self.fee_uniform.id,
                "term": self.term_1.id,
                "student_ids": [self.student_a.id],
                "allow_repeat": "true",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["assigned_count"], 1)

    def test_allow_repeat_integer_values_handled(self):
        """bulk_assign with 1 enables repeat, 0 disables repeat."""
        FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )

        # 0 -> skipped
        res_0 = self.client.post(
            "/api/finance/student-fee-assignments/bulk_assign/",
            {
                "fee_structure": self.fee_uniform.id,
                "term": self.term_1.id,
                "student_ids": [self.student_a.id],
                "allow_repeat": 0,
            },
            format="json",
        )
        self.assertEqual(res_0.status_code, status.HTTP_200_OK)
        self.assertEqual(res_0.data["assigned_count"], 0)

        # 1 -> created charge #2
        res_1 = self.client.post(
            "/api/finance/student-fee-assignments/bulk_assign/",
            {
                "fee_structure": self.fee_uniform.id,
                "term": self.term_1.id,
                "student_ids": [self.student_a.id],
                "allow_repeat": 1,
            },
            format="json",
        )
        self.assertEqual(res_1.status_code, status.HTTP_200_OK)
        self.assertEqual(res_1.data["assigned_count"], 1)

    def test_allow_repeat_null_defaults_to_false(self):
        """bulk_assign with null allow_repeat defaults to False (no repeat)."""
        FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )

        res = self.client.post(
            "/api/finance/student-fee-assignments/bulk_assign/",
            {
                "fee_structure": self.fee_uniform.id,
                "term": self.term_1.id,
                "student_ids": [self.student_a.id],
                "allow_repeat": None,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["assigned_count"], 0)
        self.assertEqual(res.data["skipped_count"], 1)

    def test_allow_repeat_malformed_values_rejected_with_http_400(self):
        """bulk_assign with malformed allow_repeat (like list or non-boolean string) returns HTTP 400."""
        res_list = self.client.post(
            "/api/finance/student-fee-assignments/bulk_assign/",
            {
                "fee_structure": self.fee_uniform.id,
                "term": self.term_1.id,
                "student_ids": [self.student_a.id],
                "allow_repeat": ["invalid"],
            },
            format="json",
        )
        self.assertEqual(res_list.status_code, status.HTTP_400_BAD_REQUEST)

        res_str = self.client.post(
            "/api/finance/student-fee-assignments/bulk_assign/",
            {
                "fee_structure": self.fee_uniform.id,
                "term": self.term_1.id,
                "student_ids": [self.student_a.id],
                "allow_repeat": "unrecognized_bool",
            },
            format="json",
        )
        self.assertEqual(res_str.status_code, status.HTTP_400_BAD_REQUEST)


class AuthorizationTests(BaseHardeningSetupMixin, TenantTestCase):
    """Tests verifying role-based access control for fee assignments."""

    def test_student_and_parent_forbidden_from_bulk_assign(self):
        """Student or parent users cannot call bulk_assign (HTTP 403)."""
        student_user = User.objects.create_user(
            email="student-user@test.local", password="password", is_student=True
        )
        client = APIClient(HTTP_HOST=self.domain.domain)
        client.force_authenticate(user=student_user)

        res = client.post(
            "/api/finance/student-fee-assignments/bulk_assign/",
            {
                "fee_structure": self.fee_uniform.id,
                "term": self.term_1.id,
                "student_ids": [self.student_a.id],
                "allow_repeat": True,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_teacher_without_finance_permission_forbidden(self):
        """Teacher without accountant or admin authority cannot create fee assignments (HTTP 403)."""
        teacher_user = User.objects.create_user(
            email="teacher-user@test.local", password="password", is_teacher=True
        )
        client = APIClient(HTTP_HOST=self.domain.domain)
        client.force_authenticate(user=teacher_user)

        res = client.post(
            "/api/finance/student-fee-assignments/bulk_assign/",
            {
                "fee_structure": self.fee_uniform.id,
                "term": self.term_1.id,
                "student_ids": [self.student_a.id],
                "allow_repeat": True,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class OptionalServiceAndRecurrenceTests(BaseHardeningSetupMixin, TenantTestCase):
    """Tests covering optional services, subscription sync, and recurrence identity across fee structures."""

    def test_automatic_subscription_sync_never_creates_repeat_charges(self):
        """Optional service subscriptions assigned via sync remain idempotent with charge_number=1."""
        service = OptionalService.objects.create(
            name="School Bus Transport",
            description="Daily transport service",
            fee_type=FeeType.OTHER,
            is_active=True,
        )
        fee_transport = FeeStructure.objects.create(
            name="Bus Transport Fee",
            amount=Decimal("20000.00"),
            fee_type=FeeType.OTHER,
            recurrence=FeeRecurrence.PER_TERM,
            academic_year=self.year_1,
            term=self.term_1,
            optional_service=service,
            is_mandatory=False,
            created_by=self.accountant,
        )
        ServiceSubscription.objects.create(
            student=self.student_a,
            service=service,
            is_active=True,
        )

        FeeAssignmentService.sync_fees_for_enrollment(enrollment=self.enrollment_a)
        FeeAssignmentService.sync_fees_for_enrollment(enrollment=self.enrollment_a)

        assignments = StudentFeeAssignment.objects.filter(
            student=self.student_a, fee_structure=fee_transport
        )
        self.assertEqual(assignments.count(), 1)
        self.assertEqual(assignments.first().charge_number, 1)

    def test_onetime_fee_with_same_logical_key_across_different_structures(self):
        """Two FeeStructures sharing logical_fee_key enforce lifetime identity for ONE_TIME recurrence."""
        fs1 = self.fee_admission  # logical_key="admission-fee"
        fs2 = FeeStructure.objects.create(
            name="Admission Fee Copy",
            amount=Decimal("50000.00"),
            fee_type=FeeType.ADMISSION,
            recurrence=FeeRecurrence.ONE_TIME,
            academic_year=self.year_2,
            term=self.term_yr2,
            logical_fee_key="admission-fee",
            is_mandatory=True,
            created_by=self.accountant,
        )

        FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=fs1, allow_repeat=False
        )

        # Attempting assignment under fs2 must detect existing obligation via logical_fee_key
        existing = FeeAssignmentService.find_existing_obligation(
            student=self.student_a, fee_structure=fs2
        )
        self.assertIsNotNone(existing)
        self.assertEqual(existing.logical_fee_key, "admission-fee")

    def test_annual_fee_with_same_logical_key_across_different_years_allowed_once_per_year(self):
        """ANNUAL fee with same logical key is allowed once in year 1 and once in year 2."""
        fs_yr1 = self.fee_dev_levy  # 2028/2029
        fs_yr2 = FeeStructure.objects.create(
            name="Development Levy Year 2",
            amount=Decimal("35000.00"),
            fee_type=FeeType.MAINTENANCE,
            recurrence=FeeRecurrence.ANNUAL,
            academic_year=self.year_2,
            term=self.term_yr2,
            logical_fee_key="dev-levy",
            is_mandatory=True,
            created_by=self.accountant,
        )

        a1 = FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=fs_yr1, term=self.term_1, allow_repeat=False
        )
        a2 = FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=fs_yr2, term=self.term_yr2, allow_repeat=False
        )
        self.assertEqual(a1.charge_number, 1)
        self.assertEqual(a2.charge_number, 1)
        self.assertEqual(a1.academic_year, self.year_1)
        self.assertEqual(a2.academic_year, self.year_2)


class SnapshotMutationTests(BaseHardeningSetupMixin, TenantTestCase):
    """Tests proving historical metadata snapshots are preserved when FeeStructures or schedules mutate."""

    def test_fee_structure_amount_mutation_does_not_alter_existing_charge(self):
        """Mutating FeeStructure.amount preserves existing assignment snapshot and applies to repeat."""
        a1 = FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )
        self.assertEqual(a1.amount_owed, Decimal("15000.00"))

        # Mutate fee structure price from 15,000 to 20,000
        self.fee_uniform.amount = Decimal("20000.00")
        self.fee_uniform.save(update_fields=["amount"])

        # Repeat assignment created months later
        a2 = FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=True
        )

        a1.refresh_from_db()
        self.assertEqual(a1.amount_owed, Decimal("15000.00"), "Old charge amount must not mutate")
        self.assertEqual(a2.amount_owed, Decimal("20000.00"), "New charge must snapshot updated price")

    def test_fee_term_schedule_mutation_preserves_historical_snapshots(self):
        """Mutating FeeTermSchedule amount preserves prior assignment snapshot."""
        fee_club = FeeStructure.objects.create(
            name="Robotics Club",
            amount=Decimal("10000.00"),
            fee_type=FeeType.OTHER,
            recurrence=FeeRecurrence.PER_TERM,
            academic_year=self.year_1,
            is_mandatory=False,
            created_by=self.accountant,
        )
        schedule = FeeTermSchedule.objects.create(
            fee_structure=fee_club,
            term=self.term_1,
            amount=Decimal("10000.00"),
            due_date=date(2028, 10, 15),
        )

        a1 = FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=fee_club, term=self.term_1, allow_repeat=False
        )
        self.assertEqual(a1.amount_owed, Decimal("10000.00"))

        # Update schedule amount
        schedule.amount = Decimal("12000.00")
        schedule.save(update_fields=["amount"])

        a1.refresh_from_db()
        self.assertEqual(a1.amount_owed, Decimal("10000.00"))


class PaymentWaiverAdjustmentReportingTests(BaseHardeningSetupMixin, TenantTestCase):
    """Tests verifying payments, reversals, waivers, adjustments, and reporting across repeated charges."""

    def test_partial_payment_and_over_allocation_integrity(self):
        """Payment can allocate partially against Charge #2; over-allocation is rejected atomically."""
        a1 = FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )
        a2 = FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=True
        )

        # Pay 5,000 on a2
        PaymentAllocationService.record_payment_with_allocations(
            receipt_data={
                "payer": "Parent",
                "paid_through": "Cash",
                "payment_date": date(2028, 9, 20),
            },
            allocations=[{"fee_assignment": a2.pk, "amount": "5000.00"}],
            received_by=self.accountant,
        )
        a1.refresh_from_db()
        a2.refresh_from_db()
        self.assertEqual(a1.balance, Decimal("15000.00"))
        self.assertEqual(a2.balance, Decimal("10000.00"))

        # Attempting over-allocation on a2 (> 10,000)
        with self.assertRaises(ValidationError):
            PaymentAllocationService.record_payment_with_allocations(
                receipt_data={
                    "payer": "Parent",
                    "paid_through": "Cash",
                    "payment_date": date(2028, 9, 21),
                },
                allocations=[{"fee_assignment": a2.pk, "amount": "15000.00"}],
                received_by=self.accountant,
            )

    def test_duplicate_assignment_in_single_receipt_payload_rejected(self):
        """Providing the same fee_assignment twice in one receipt allocation payload is rejected."""
        a = FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )
        with self.assertRaises(ValidationError) as ctx:
            PaymentAllocationService.record_payment_with_allocations(
                receipt_data={
                    "payer": "Parent",
                    "paid_through": "Cash",
                    "payment_date": date(2028, 9, 20),
                },
                allocations=[
                    {"fee_assignment": a.pk, "amount": "5000.00"},
                    {"fee_assignment": a.pk, "amount": "5000.00"},
                ],
                received_by=self.accountant,
            )
        self.assertIn("Duplicate fee assignment", str(ctx.exception))

    def test_mixed_receipt_with_mandatory_and_multiple_repeated_charges(self):
        """Single receipt allocates across mandatory tuition and multiple uniform repeat charges."""
        a_tuition = FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=self.fee_tuition, term=self.term_1, allow_repeat=False
        )
        a_u1 = FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )
        a_u2 = FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=True
        )

        receipt = PaymentAllocationService.record_payment_with_allocations(
            receipt_data={
                "payer": "Parent",
                "paid_through": "Bank Transfer",
                "payment_date": date(2028, 9, 20),
            },
            allocations=[
                {"fee_assignment": a_tuition.pk, "amount": "100000.00"},
                {"fee_assignment": a_u1.pk, "amount": "15000.00"},
                {"fee_assignment": a_u2.pk, "amount": "15000.00"},
            ],
            received_by=self.accountant,
        )
        self.assertEqual(receipt.amount, Decimal("130000.00"))
        self.assertEqual(receipt.fee_allocations.count(), 3)

    def test_receipt_reversal_restores_balances_on_all_repeated_charges(self):
        """Reversing a receipt restores amount_paid and balance across all allocated repeat charges."""
        a1 = FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )
        a2 = FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=True
        )

        receipt = PaymentAllocationService.record_payment_with_allocations(
            receipt_data={
                "payer": "Parent",
                "paid_through": "Bank Transfer",
                "payment_date": date(2028, 9, 20),
            },
            allocations=[
                {"fee_assignment": a1.pk, "amount": "15000.00"},
                {"fee_assignment": a2.pk, "amount": "15000.00"},
            ],
            received_by=self.accountant,
        )

        # Reverse receipt
        PaymentAllocationService.reverse_receipt(
            receipt=receipt,
            actor=self.accountant,
        )
        a1.refresh_from_db()
        a2.refresh_from_db()
        self.assertEqual(a1.amount_paid, Decimal("0.00"))
        self.assertEqual(a1.balance, Decimal("15000.00"))
        self.assertEqual(a2.amount_paid, Decimal("0.00"))
        self.assertEqual(a2.balance, Decimal("15000.00"))
        self.assertFalse(Receipt.objects.filter(pk=receipt.pk).exists())

    def test_fee_adjustment_applies_to_specific_charge_assignment(self):
        """FeeAdjustment records adjust amount_owed on specific charge without affecting siblings."""
        a1 = FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )
        a2 = FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=True
        )

        a1.adjust_amount(Decimal("12000.00"), reason="Damaged item discount on charge 1")

        a1.refresh_from_db()
        a2.refresh_from_db()
        self.assertEqual(a1.amount_owed, Decimal("12000.00"))
        self.assertEqual(a1.balance, Decimal("12000.00"))
        self.assertEqual(a2.amount_owed, Decimal("15000.00"))
        self.assertEqual(a2.balance, Decimal("15000.00"))
        self.assertEqual(a1.adjustments.count(), 1)
        self.assertEqual(a2.adjustments.count(), 0)

    def test_waiver_on_charge_1_does_not_affect_charge_2(self):
        """Waiving Charge #1 leaves Charge #2 active and creating Charge #2 does not inherit waiver."""
        a1 = FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )
        a1.waive_fee(reason="Scholarship uniform grant", waived_by=self.accountant)
        self.assertTrue(a1.is_waived)

        # Create repeat charge #2
        a2 = FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=True
        )
        self.assertFalse(a2.is_waived)
        self.assertEqual(a2.balance, Decimal("15000.00"))

    def test_reporting_aggregations_do_not_deduplicate_repeated_charges(self):
        """Financial obligation reports sum distinct rows without accidental key deduplication."""
        FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=self.fee_tuition, term=self.term_1, allow_repeat=False
        )
        FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )
        FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=True
        )

        # Total expected = 100,000 + 15,000 + 15,000 = 130,000
        total_owed = StudentFeeAssignment.objects.filter(
            student=self.student_a
        ).aggregate(total=models.Sum("amount_owed"))["total"]
        self.assertEqual(total_owed, Decimal("130000.00"))

    def test_bulk_assign_multi_student_partial_success(self):
        """Bulk assign reports created count and skipped count accurately across multiple students."""
        # Pre-assign Uniform to student_a
        FeeAssignmentService.assign_fee_to_student(
            student=self.student_a, fee_structure=self.fee_uniform, term=self.term_1, allow_repeat=False
        )

        # Bulk assign with allow_repeat=False for student_a and student_b
        res = self.client.post(
            "/api/finance/student-fee-assignments/bulk_assign/",
            {
                "fee_structure": self.fee_uniform.id,
                "term": self.term_1.id,
                "student_ids": [self.student_a.id, self.student_b.id],
                "allow_repeat": False,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["assigned_count"], 1)  # student_b created
        self.assertEqual(res.data["skipped_count"], 1)   # student_a skipped
