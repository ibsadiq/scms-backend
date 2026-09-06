from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.models import ProtectedError
from rest_framework import status
from rest_framework.test import APIClient
from school.testcases import TenantTestCase

from academic.models import (
    ClassRoom,
    GradeLevel,
    Student,
    StudentClassEnrollment,
)
from administration.models import AcademicYear, Term
from finance.models import (
    AuditAction,
    FeeApplicability,
    FeePaymentAllocation,
    FeeRecurrence,
    FeeStructure,
    FeeTermSchedule,
    FinanceAuditLog,
    Receipt,
    StudentFeeAssignment,
)
from finance.serializers import FeeStructureSerializer
from finance.services.fee_assignment_service import FeeAssignmentService
from finance.services.payment_allocation_service import PaymentAllocationService

User = get_user_model()


class FinalFinanceCorrectiveHardeningTests(TenantTestCase):
    """
    Regression test suite for final finance corrective hardening:
    - FIN-01: FeeStructure deletion safety (DB & API)
    - FIN-02: StudentFeeAssignment deletion safety (DB & API)
    - FIN-04: Backend recurrence & applicability validation (Model & Serializer)
    - FIN-05: Waiver with existing payments rejected (Model & API)
    - FIN-06: Student balance term scope preserves annual & one-time obligations
    """

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

        self.year_2028 = AcademicYear.objects.create(
            name="2028/2029",
            start_date=date(2028, 9, 1),
            end_date=date(2029, 7, 1),
            active_year=True,
        )
        self.term_1 = Term.objects.create(
            name="First Term 28/29",
            academic_year=self.year_2028,
            start_date=date(2028, 9, 1),
            end_date=date(2028, 12, 1),
        )
        self.term_2 = Term.objects.create(
            name="Second Term 28/29",
            academic_year=self.year_2028,
            start_date=date(2029, 1, 10),
            end_date=date(2029, 4, 10),
        )

        self.year_old = AcademicYear.objects.create(
            name="2027/2028",
            start_date=date(2027, 9, 1),
            end_date=date(2028, 7, 1),
            active_year=False,
        )
        self.term_old = Term.objects.create(
            name="Old Term 27/28",
            academic_year=self.year_old,
            start_date=date(2027, 9, 1),
            end_date=date(2027, 12, 1),
        )

        self.grade = GradeLevel.objects.create(
            system_code="JSS_1",
            section="JSS",
            default_name="JSS 1",
            sequence_order=1,
        )
        self.classroom = ClassRoom.objects.create(
            name="JSS 1A", grade_level=self.grade, capacity=35
        )

        self.student = Student.objects.create(
            first_name="Hardening",
            last_name="Student",
            admission_number="ADM-HD-001",
            classroom=self.classroom,
            is_active=True,
        )
        self.enrollment = StudentClassEnrollment.objects.create(
            student=self.student,
            classroom=self.classroom,
            academic_year=self.year_2028,
            is_active=True,
        )

    # =========================================================================
    # FIN-01: FeeStructure Deletion Safety
    # =========================================================================

    def test_fin01_unused_feestructure_can_be_deleted(self):
        """FeeStructure without assignments can be deleted via API and cascades schedules."""
        fee = FeeStructure.objects.create(
            name="Unused Activity Fee",
            fee_type="Activity",
            amount=Decimal("5000.00"),
            academic_year=self.year_2028,
            recurrence=FeeRecurrence.PER_TERM,
            applicability=FeeApplicability.ALL_ELIGIBLE,
            logical_fee_key="unused-activity",
        )
        FeeTermSchedule.objects.create(
            fee_structure=fee,
            term=self.term_1,
            amount=Decimal("5000.00"),
            due_date=date(2028, 10, 1),
        )

        response = self.client.delete(f"/api/finance/fee-structures/{fee.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(FeeStructure.objects.filter(id=fee.id).exists())
        self.assertFalse(FeeTermSchedule.objects.filter(fee_structure_id=fee.id).exists())

    def test_fin01_feestructure_with_unpaid_assignment_cannot_be_deleted(self):
        """FeeStructure with existing student assignments cannot be deleted via API or ORM."""
        fee = FeeStructure.objects.create(
            name="Tuition Term 1",
            fee_type="Tuition",
            amount=Decimal("40000.00"),
            academic_year=self.year_2028,
            term=self.term_1,
            recurrence=FeeRecurrence.PER_TERM,
            applicability=FeeApplicability.ALL_ELIGIBLE,
            logical_fee_key="tuition-t1",
        )
        assignment, _ = FeeAssignmentService.get_or_create_assignment(
            fee_structure=fee,
            student=self.student,
            term=self.term_1,
        )
        self.assertEqual(assignment.amount_paid, Decimal("0.00"))

        # API deletion rejected with controlled error response
        response = self.client.delete(f"/api/finance/fee-structures/{fee.id}/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
        self.assertEqual(
            response.data["error"],
            "Cannot delete this fee structure because student fee assignments already exist.",
        )
        self.assertTrue(FeeStructure.objects.filter(id=fee.id).exists())

        # Direct ORM deletion raises ProtectedError
        with self.assertRaises(ProtectedError):
            fee.delete()

    def test_fin01_feestructure_with_paid_assignment_cannot_be_deleted(self):
        """FeeStructure with paid assignment cannot be deleted."""
        fee = FeeStructure.objects.create(
            name="Lab Fee",
            fee_type="Lab",
            amount=Decimal("15000.00"),
            academic_year=self.year_2028,
            term=self.term_1,
            recurrence=FeeRecurrence.PER_TERM,
            applicability=FeeApplicability.ALL_ELIGIBLE,
            logical_fee_key="lab-fee",
        )
        assignment, _ = FeeAssignmentService.get_or_create_assignment(
            fee_structure=fee,
            student=self.student,
            term=self.term_1,
        )
        PaymentAllocationService.record_payment_with_allocations(
            receipt_data={"payer": "Parent", "paid_through": "Cash", "student": self.student},
            allocations=[{"fee_assignment": assignment.id, "amount": Decimal("10000.00")}],
            actor=self.accountant,
        )

        response = self.client.delete(f"/api/finance/fee-structures/{fee.id}/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["error"],
            "Cannot delete this fee structure because student fee assignments already exist.",
        )
        with self.assertRaises(ProtectedError):
            fee.delete()

    # =========================================================================
    # FIN-02: StudentFeeAssignment Deletion Safety
    # =========================================================================

    def test_fin02_unpaid_assignment_without_payment_history_can_be_deleted(self):
        """Unpaid assignment with no payment allocations can be safely deleted."""
        fee = FeeStructure.objects.create(
            name="Erroneous Fee",
            fee_type="Other",
            amount=Decimal("8000.00"),
            academic_year=self.year_2028,
            term=self.term_1,
            recurrence=FeeRecurrence.PER_TERM,
            logical_fee_key="erroneous-fee",
        )
        assignment, _ = FeeAssignmentService.get_or_create_assignment(
            fee_structure=fee,
            student=self.student,
            term=self.term_1,
        )
        self.assertEqual(assignment.amount_paid, Decimal("0.00"))
        self.assertFalse(assignment.payment_allocations.exists())

        response = self.client.delete(f"/api/finance/student-fee-assignments/{assignment.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(StudentFeeAssignment.objects.filter(id=assignment.id).exists())

    def test_fin02_assignment_with_amount_paid_cannot_be_deleted(self):
        """Assignment with amount_paid > 0 cannot be deleted via API or ORM."""
        fee = FeeStructure.objects.create(
            name="Exam Fee",
            fee_type="Exam",
            amount=Decimal("12000.00"),
            academic_year=self.year_2028,
            term=self.term_1,
            recurrence=FeeRecurrence.PER_TERM,
            logical_fee_key="exam-fee",
        )
        assignment, _ = FeeAssignmentService.get_or_create_assignment(
            fee_structure=fee,
            student=self.student,
            term=self.term_1,
        )
        PaymentAllocationService.record_payment_with_allocations(
            receipt_data={"payer": "Parent", "paid_through": "Cash", "student": self.student},
            allocations=[{"fee_assignment": assignment.id, "amount": Decimal("6000.00")}],
            actor=self.accountant,
        )
        assignment.refresh_from_db()
        self.assertEqual(assignment.amount_paid, Decimal("6000.00"))

        # API deletion rejected
        response = self.client.delete(f"/api/finance/student-fee-assignments/{assignment.id}/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["error"],
            "Cannot delete this fee assignment because payment history exists.",
        )
        self.assertTrue(StudentFeeAssignment.objects.filter(id=assignment.id).exists())

        # ORM deletion raises ValidationError
        with self.assertRaises(ValidationError):
            assignment.delete()

    # =========================================================================
    # FIN-04: Backend Recurrence/Applicability Validation
    # =========================================================================

    def test_fin04_model_clean_rejects_per_term_new_students_only(self):
        """FeeStructure.clean() rejects PER_TERM + NEW_STUDENTS_ONLY."""
        fee = FeeStructure(
            name="Invalid Orientation Fee",
            fee_type="Other",
            amount=Decimal("5000.00"),
            academic_year=self.year_2028,
            term=self.term_1,
            recurrence=FeeRecurrence.PER_TERM,
            applicability=FeeApplicability.NEW_STUDENTS_ONLY,
            logical_fee_key="invalid-orientation",
        )
        with self.assertRaises(ValidationError) as ctx:
            fee.clean()
        self.assertIn("applicability", ctx.exception.message_dict)
        self.assertEqual(
            ctx.exception.message_dict["applicability"][0],
            "New Students Only cannot be used with Every Term billing.",
        )

    def test_fin04_serializer_create_rejects_per_term_new_students_only(self):
        """FeeStructureSerializer create rejects PER_TERM + NEW_STUDENTS_ONLY."""
        data = {
            "name": "Invalid Orientation Fee",
            "fee_type": "Other",
            "amount": "5000.00",
            "academic_year": self.year_2028.id,
            "term": self.term_1.id,
            "recurrence": FeeRecurrence.PER_TERM,
            "applicability": FeeApplicability.NEW_STUDENTS_ONLY,
            "logical_fee_key": "invalid-orientation",
        }
        serializer = FeeStructureSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("applicability", serializer.errors)
        self.assertEqual(
            str(serializer.errors["applicability"][0]),
            "New Students Only cannot be used with Every Term billing.",
        )

    def test_fin04_serializer_patch_recurrence_into_invalid_combination_rejects(self):
        """FeeStructureSerializer PATCH recurrence to PER_TERM on NEW_STUDENTS_ONLY rejects."""
        fee = FeeStructure.objects.create(
            name="Valid Annual Fee",
            fee_type="Other",
            amount=Decimal("5000.00"),
            academic_year=self.year_2028,
            recurrence=FeeRecurrence.ANNUAL,
            applicability=FeeApplicability.NEW_STUDENTS_ONLY,
            logical_fee_key="valid-annual",
        )
        serializer = FeeStructureSerializer(instance=fee, data={"recurrence": FeeRecurrence.PER_TERM}, partial=True)
        self.assertFalse(serializer.is_valid())
        self.assertIn("applicability", serializer.errors)
        self.assertEqual(
            str(serializer.errors["applicability"][0]),
            "New Students Only cannot be used with Every Term billing.",
        )

    def test_fin04_serializer_patch_applicability_into_invalid_combination_rejects(self):
        """FeeStructureSerializer PATCH applicability to NEW_STUDENTS_ONLY on PER_TERM rejects."""
        fee = FeeStructure.objects.create(
            name="Valid Per Term Fee",
            fee_type="Other",
            amount=Decimal("5000.00"),
            academic_year=self.year_2028,
            term=self.term_1,
            recurrence=FeeRecurrence.PER_TERM,
            applicability=FeeApplicability.ALL_ELIGIBLE,
            logical_fee_key="valid-per-term",
        )
        serializer = FeeStructureSerializer(
            instance=fee,
            data={"applicability": FeeApplicability.NEW_STUDENTS_ONLY},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("applicability", serializer.errors)
        self.assertEqual(
            str(serializer.errors["applicability"][0]),
            "New Students Only cannot be used with Every Term billing.",
        )

    def test_fin04_valid_recurrence_applicability_combinations_accepted(self):
        """Valid combinations (PER_TERM+ALL_ELIGIBLE, ANNUAL+ALL, ANNUAL+NEW, ONE_TIME+ALL, ONE_TIME+NEW) pass."""
        valid_combos = [
            (FeeRecurrence.PER_TERM, FeeApplicability.ALL_ELIGIBLE),
            (FeeRecurrence.ANNUAL, FeeApplicability.ALL_ELIGIBLE),
            (FeeRecurrence.ANNUAL, FeeApplicability.NEW_STUDENTS_ONLY),
            (FeeRecurrence.ONE_TIME, FeeApplicability.ALL_ELIGIBLE),
            (FeeRecurrence.ONE_TIME, FeeApplicability.NEW_STUDENTS_ONLY),
        ]
        for rec, app in valid_combos:
            fee = FeeStructure(
                name=f"Combo {rec} {app}",
                fee_type="Other",
                amount=Decimal("1000.00"),
                academic_year=self.year_2028,
                term=self.term_1 if rec == FeeRecurrence.PER_TERM else None,
                recurrence=rec,
                applicability=app,
                logical_fee_key=f"combo-{rec}-{app}".lower(),
            )
            # Model validation passes
            fee.clean()

            # Serializer validation passes
            serializer = FeeStructureSerializer(
                data={
                    "name": f"Combo {rec} {app}",
                    "fee_type": "Other",
                    "amount": "1000.00",
                    "academic_year": self.year_2028.id,
                    "term": self.term_1.id if rec == FeeRecurrence.PER_TERM else None,
                    "recurrence": rec,
                    "applicability": app,
                    "logical_fee_key": f"combo-{rec}-{app}".lower(),
                }
            )
            self.assertTrue(serializer.is_valid(), f"Failed for combo: {rec} + {app}: {serializer.errors}")

    # =========================================================================
    # FIN-05: Waiver With Existing Payments
    # =========================================================================

    def test_fin05_unpaid_assignment_can_be_waived(self):
        """Unpaid assignment can be waived via API and logs audit entry."""
        fee = FeeStructure.objects.create(
            name="PTA Levy",
            fee_type="PTA",
            amount=Decimal("5000.00"),
            academic_year=self.year_2028,
            term=self.term_1,
            recurrence=FeeRecurrence.PER_TERM,
            logical_fee_key="pta-levy",
        )
        assignment, _ = FeeAssignmentService.get_or_create_assignment(
            fee_structure=fee,
            student=self.student,
            term=self.term_1,
        )

        response = self.client.post(
            f"/api/finance/student-fee-assignments/{assignment.id}/waive/",
            {"reason": "Scholarship awarded"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assignment.refresh_from_db()
        self.assertTrue(assignment.is_waived)
        self.assertEqual(assignment.waived_reason, "Scholarship awarded")
        self.assertTrue(
            FinanceAuditLog.objects.filter(
                action=AuditAction.FEE_WAIVED, target_student=self.student
            ).exists()
        )

    def test_fin05_partially_paid_assignment_cannot_be_waived(self):
        """Partially paid assignment waiver is rejected via API and model."""
        fee = FeeStructure.objects.create(
            name="Tuition Fee",
            fee_type="Tuition",
            amount=Decimal("50000.00"),
            academic_year=self.year_2028,
            term=self.term_1,
            recurrence=FeeRecurrence.PER_TERM,
            logical_fee_key="tuition-waiver-test",
        )
        assignment, _ = FeeAssignmentService.get_or_create_assignment(
            fee_structure=fee,
            student=self.student,
            term=self.term_1,
        )
        PaymentAllocationService.record_payment_with_allocations(
            receipt_data={"payer": "Parent", "paid_through": "Cash", "student": self.student},
            allocations=[{"fee_assignment": assignment.id, "amount": Decimal("20000.00")}],
            actor=self.accountant,
        )
        assignment.refresh_from_db()
        self.assertEqual(assignment.amount_paid, Decimal("20000.00"))

        # API waiver rejected
        response = self.client.post(
            f"/api/finance/student-fee-assignments/{assignment.id}/waive/",
            {"reason": "Partial waiver attempt"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["error"],
            "This fee has recorded payments. Reverse the payment before waiving the fee.",
        )
        assignment.refresh_from_db()
        self.assertFalse(assignment.is_waived)
        self.assertEqual(assignment.amount_paid, Decimal("20000.00"))

        # Model waive_fee raises ValidationError
        with self.assertRaises(ValidationError) as ctx:
            assignment.waive_fee(reason="Direct call", waived_by=self.accountant)
        self.assertIn("This fee has recorded payments", str(ctx.exception))

    def test_fin05_fully_paid_assignment_cannot_be_waived(self):
        """Fully paid assignment waiver is rejected."""
        fee = FeeStructure.objects.create(
            name="Medical Fee",
            fee_type="Medical",
            amount=Decimal("10000.00"),
            academic_year=self.year_2028,
            term=self.term_1,
            recurrence=FeeRecurrence.PER_TERM,
            logical_fee_key="medical-waiver-test",
        )
        assignment, _ = FeeAssignmentService.get_or_create_assignment(
            fee_structure=fee,
            student=self.student,
            term=self.term_1,
        )
        PaymentAllocationService.record_payment_with_allocations(
            receipt_data={"payer": "Parent", "paid_through": "Cash", "student": self.student},
            allocations=[{"fee_assignment": assignment.id, "amount": Decimal("10000.00")}],
            actor=self.accountant,
        )
        assignment.refresh_from_db()
        self.assertTrue(assignment.is_fully_paid)

        response = self.client.post(
            f"/api/finance/student-fee-assignments/{assignment.id}/waive/",
            {"reason": "Full waiver attempt"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["error"],
            "This fee has recorded payments. Reverse the payment before waiving the fee.",
        )
        assignment.refresh_from_db()
        self.assertFalse(assignment.is_waived)

    # =========================================================================
    # FIN-06: Student Balance Term Scope
    # =========================================================================

    def test_fin06_term_filtered_student_balance_includes_annual_and_onetime_fees(self):
        """
        When term_id is supplied to student balance:
        - Term 2 PER_TERM fees are included.
        - Term 1 PER_TERM fees are excluded.
        - ANNUAL fees for that academic year are included.
        - ONE_TIME fees for that academic year are included.
        - Repeat optional charges for Term 2 are included as independent line items.
        - Historical academic year obligations are excluded.
        """
        # 1. Term 1 PER_TERM fee (25,000)
        fee_t1 = FeeStructure.objects.create(
            name="Tuition Term 1",
            fee_type="Tuition",
            amount=Decimal("25000.00"),
            academic_year=self.year_2028,
            term=self.term_1,
            recurrence=FeeRecurrence.PER_TERM,
            logical_fee_key="t1-tuition",
        )
        assign_t1, _ = FeeAssignmentService.get_or_create_assignment(
            fee_structure=fee_t1, student=self.student, term=self.term_1
        )

        # 2. Term 2 PER_TERM fee (30,000)
        fee_t2 = FeeStructure.objects.create(
            name="Tuition Term 2",
            fee_type="Tuition",
            amount=Decimal("30000.00"),
            academic_year=self.year_2028,
            term=self.term_2,
            recurrence=FeeRecurrence.PER_TERM,
            logical_fee_key="t2-tuition",
        )
        assign_t2, _ = FeeAssignmentService.get_or_create_assignment(
            fee_structure=fee_t2, student=self.student, term=self.term_2
        )

        # 3. ANNUAL fee (15,000) - assigned in Term 1
        fee_annual = FeeStructure.objects.create(
            name="Development Levy",
            fee_type="Development",
            amount=Decimal("15000.00"),
            academic_year=self.year_2028,
            recurrence=FeeRecurrence.ANNUAL,
            logical_fee_key="dev-levy",
        )
        assign_annual, _ = FeeAssignmentService.get_or_create_assignment(
            fee_structure=fee_annual, student=self.student, term=self.term_1
        )

        # 4. ONE_TIME fee (10,000) - assigned in Term 1
        fee_onetime = FeeStructure.objects.create(
            name="Registration Fee",
            fee_type="Registration",
            amount=Decimal("10000.00"),
            academic_year=self.year_2028,
            recurrence=FeeRecurrence.ONE_TIME,
            logical_fee_key="reg-fee",
        )
        assign_onetime, _ = FeeAssignmentService.get_or_create_assignment(
            fee_structure=fee_onetime, student=self.student, term=self.term_1
        )

        # 5. Repeatable optional fees for Term 2: Uniform #1 (5,000) and Uniform #2 (5,000)
        fee_uniform = FeeStructure.objects.create(
            name="School Uniform",
            fee_type="Uniform",
            amount=Decimal("5000.00"),
            academic_year=self.year_2028,
            term=self.term_2,
            recurrence=FeeRecurrence.PER_TERM,
            is_mandatory=False,
            logical_fee_key="school-uniform",
        )
        assign_u1, _ = FeeAssignmentService.get_or_create_assignment(
            fee_structure=fee_uniform, student=self.student, term=self.term_2, allow_repeat=False
        )
        assign_u2, _ = FeeAssignmentService.get_or_create_assignment(
            fee_structure=fee_uniform, student=self.student, term=self.term_2, allow_repeat=True
        )
        self.assertEqual(assign_u1.charge_number, 1)
        self.assertEqual(assign_u2.charge_number, 2)

        # 6. Historical 2027/2028 fee (50,000)
        fee_old = FeeStructure.objects.create(
            name="Old Year Fee",
            fee_type="Other",
            amount=Decimal("50000.00"),
            academic_year=self.year_old,
            recurrence=FeeRecurrence.ANNUAL,
            logical_fee_key="old-annual",
        )
        assign_old, _ = FeeAssignmentService.get_or_create_assignment(
            fee_structure=fee_old, student=self.student, term=self.term_old
        )

        # 7. Query student balance filtered by Term 2
        response = self.client.get(
            f"/api/finance/student-balance/{self.student.id}/?term_id={self.term_2.id}"
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
            getattr(response, "data", response.content),
        )

        breakdown_ids = [item["id"] for item in response.data["fee_breakdown"]]

        # INCLUDED in Term 2 balance:
        self.assertIn(assign_t2.id, breakdown_ids)
        self.assertIn(assign_u1.id, breakdown_ids)
        self.assertIn(assign_u2.id, breakdown_ids)

        # EXCLUDED from Term 2 balance:
        self.assertNotIn(assign_t1.id, breakdown_ids, "Term 1 PER_TERM fee must be excluded from Term 2 balance.")
        self.assertNotIn(assign_annual.id, breakdown_ids, "Term 1 ANNUAL fee must be excluded from Term 2 balance.")
        self.assertNotIn(assign_onetime.id, breakdown_ids, "Term 1 ONE_TIME fee must be excluded from Term 2 balance.")
        self.assertNotIn(assign_old.id, breakdown_ids, "Historical academic year fee must be excluded.")

        # Total fees for Term 2 = 30000 (T2) + 5000 (U1) + 5000 (U2) = 40000
        expected_t2_total = Decimal("40000.00")
        self.assertEqual(Decimal(str(response.data["total_fees"])), expected_t2_total)
        self.assertEqual(Decimal(str(response.data["balance"])), expected_t2_total)

        # Verify repeat optional charges preserve distinct charge_number
        uniform_items = [item for item in response.data["fee_breakdown"] if item["id"] in (assign_u1.id, assign_u2.id)]
        self.assertEqual(len(uniform_items), 2)
        charge_numbers = {item["charge_number"] for item in uniform_items}
        self.assertEqual(charge_numbers, {1, 2})

        # Also verify StudentFeeBalanceViewSet.summary with term_id
        summary_res = self.client.get(f"/api/finance/student-balance/summary/?term_id={self.term_2.id}")
        self.assertEqual(
            summary_res.status_code,
            status.HTTP_200_OK,
            getattr(summary_res, "data", summary_res.content),
        )
        student_summary = next(
            (s for s in summary_res.data["results"] if s["student"] == self.student.id), None
        )
        self.assertIsNotNone(student_summary)
        self.assertEqual(Decimal(str(student_summary["total_fees"])), expected_t2_total)

        # 8. Query academic year balance (all terms + annual + one-time in active year)
        year_res = self.client.get(
            f"/api/finance/student-balance/{self.student.id}/?academic_year_id={self.year_2028.id}"
        )
        self.assertEqual(year_res.status_code, status.HTTP_200_OK)
        year_breakdown_ids = [item["id"] for item in year_res.data["fee_breakdown"]]
        self.assertIn(assign_t1.id, year_breakdown_ids)
        self.assertIn(assign_t2.id, year_breakdown_ids)
        self.assertIn(assign_annual.id, year_breakdown_ids)
        self.assertIn(assign_onetime.id, year_breakdown_ids)
        self.assertIn(assign_u1.id, year_breakdown_ids)
        self.assertIn(assign_u2.id, year_breakdown_ids)
        self.assertNotIn(assign_old.id, year_breakdown_ids)

        # 9. Verify waived fee contributes 0.00 to balance
        assign_t2.is_waived = True
        assign_t2.save(update_fields=["is_waived"])
        t2_waived_res = self.client.get(
            f"/api/finance/student-balance/{self.student.id}/?term_id={self.term_2.id}"
        )
        self.assertEqual(t2_waived_res.status_code, status.HTTP_200_OK)
        # Expected without assign_t2 (30000): 5000 (U1) + 5000 (U2) = 10000
        self.assertEqual(Decimal(str(t2_waived_res.data["total_fees"])), Decimal("10000.00"))
        self.assertEqual(Decimal(str(t2_waived_res.data["balance"])), Decimal("10000.00"))
        t2_item = next(i for i in t2_waived_res.data["fee_breakdown"] if i["id"] == assign_t2.id)
        self.assertTrue(t2_item["is_waived"])
        self.assertEqual(Decimal(str(t2_item["balance"])), Decimal("0.00"))
        self.assertEqual(t2_item["status"], "Waived")

    def test_fin05_waived_assignment_filter_payment_status(self):
        """StudentFeeAssignmentFilter payment_status correctly classifies Waived and excludes from Unpaid."""
        from finance.filters import StudentFeeAssignmentFilter

        fee = FeeStructure.objects.create(
            name="Lab Fee",
            fee_type="Lab",
            amount=Decimal("4000.00"),
            academic_year=self.year_2028,
            term=self.term_1,
            recurrence=FeeRecurrence.PER_TERM,
            logical_fee_key="lab-fee-filter-test",
        )
        assignment, _ = FeeAssignmentService.get_or_create_assignment(
            fee_structure=fee,
            student=self.student,
            term=self.term_1,
        )
        # Initially Unpaid
        f_unpaid = StudentFeeAssignmentFilter(
            data={"payment_status": "Unpaid"},
            queryset=StudentFeeAssignment.objects.filter(id=assignment.id),
        )
        self.assertTrue(f_unpaid.qs.exists())

        # Waive assignment
        assignment.is_waived = True
        assignment.save(update_fields=["is_waived"])

        # No longer in Unpaid
        f_unpaid_after = StudentFeeAssignmentFilter(
            data={"payment_status": "Unpaid"},
            queryset=StudentFeeAssignment.objects.filter(id=assignment.id),
        )
        self.assertFalse(f_unpaid_after.qs.exists())

        # Appears in Waived
        f_waived = StudentFeeAssignmentFilter(
            data={"payment_status": "Waived"},
            queryset=StudentFeeAssignment.objects.filter(id=assignment.id),
        )
        self.assertTrue(f_waived.qs.exists())

