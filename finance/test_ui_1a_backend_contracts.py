from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db import connection
from rest_framework import status
from rest_framework.test import APIClient
from school.testcases import TenantTestCase

from academic.models import ClassRoom, GradeLevel, Parent, Student, StudentClassEnrollment
from administration.models import AcademicYear, Term
from finance.models import (
    AuditAction,
    FeeApplicability,
    FeeRecurrence,
    FeeStructure,
    FinanceAuditLog,
    PaymentStatus,
    Receipt,
    StudentFeeAssignment,
)
from finance.services import FeeAssignmentService, PaymentAllocationService

User = get_user_model()


class UI1ABackendContractsTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.status = "active"
        return super().setup_tenant(tenant)

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        self.client = APIClient(HTTP_HOST=self.domain.domain)

        self.year = AcademicYear.objects.create(
            name="2026/2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 7, 1),
            active_year=True,
        )
        self.term = Term.objects.create(
            name="Term 1",
            academic_year=self.year,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 15),
        )
        self.admin = User.objects.create_user(
            email="admin@school.ng",
            password="pass",
            is_staff=True,
            is_superuser=True,
            is_admin=True,
            active_role="admin",
        )
        self.parent_user = User.objects.create_user(
            email="parent@school.ng",
            password="pass",
            is_parent=True,
            active_role="parent",
        )
        self.parent_profile = Parent.objects.create(
            user=self.parent_user,
            first_name="Emeka",
            last_name="Okafor",
            phone_number="08012345678",
        )
        self.student_user = User.objects.create_user(
            email="student@school.ng",
            password="pass",
            is_student=True,
            active_role="student",
        )
        self.grade = GradeLevel.objects.create(
            system_code="JSS_1",
            section="JSS",
            default_name="JSS 1",
            sequence_order=1,
        )
        self.classroom = ClassRoom.objects.create(
            name="JSS 1A",
            grade_level=self.grade,
            capacity=35,
        )
        self.student = Student.objects.create(
            user=self.student_user,
            first_name="Chidi",
            last_name="Okafor",
            admission_number="ADM-2026-001",
            classroom=self.classroom,
            parent_guardian=self.parent_profile,
            is_active=True,
        )
        self.enrollment = StudentClassEnrollment.objects.create(
            student=self.student,
            classroom=self.classroom,
            academic_year=self.year,
            is_active=True,
        )

        # Tuition fee (Per Term)
        self.tuition_fee = FeeStructure.objects.create(
            name="Tuition Fee",
            fee_type="Tuition",
            amount=Decimal("50000.00"),
            academic_year=self.year,
            term=self.term,
            recurrence=FeeRecurrence.PER_TERM,
            applicability=FeeApplicability.ALL_ELIGIBLE,
            is_mandatory=True,
        )
        # Development Levy (Annual)
        self.annual_fee = FeeStructure.objects.create(
            name="Development Levy",
            fee_type="Maintenance",
            amount=Decimal("20000.00"),
            academic_year=self.year,
            term=None,
            recurrence=FeeRecurrence.ANNUAL,
            logical_fee_key="DEV_LEVY",
            applicability=FeeApplicability.ALL_ELIGIBLE,
            is_mandatory=True,
        )
        # Optional Uniform (Manual, Repeatable)
        self.uniform_fee = FeeStructure.objects.create(
            name="School Uniform",
            fee_type="Uniform",
            amount=Decimal("15000.00"),
            academic_year=self.year,
            term=self.term,
            recurrence=FeeRecurrence.PER_TERM,
            applicability=FeeApplicability.ALL_ELIGIBLE,
            is_mandatory=False,
        )

        res_tuition = FeeAssignmentService.assign_fee_to_student(
            student=self.student,
            fee_structure=self.tuition_fee,
            term=self.term,
        )
        self.assignment_tuition = getattr(res_tuition, "assignment", res_tuition)

        res_annual = FeeAssignmentService.assign_fee_to_student(
            student=self.student,
            fee_structure=self.annual_fee,
            term=None,
        )
        self.assignment_annual = getattr(res_annual, "assignment", res_annual)

        res_u1 = FeeAssignmentService.assign_fee_to_student(
            student=self.student,
            fee_structure=self.uniform_fee,
            term=self.term,
        )
        self.assignment_uniform_1 = getattr(res_u1, "assignment", res_u1)

        res_u2 = FeeAssignmentService.assign_fee_to_student(
            student=self.student,
            fee_structure=self.uniform_fee,
            term=self.term,
            allow_repeat=True,
        )
        self.assignment_uniform_2 = getattr(res_u2, "assignment", res_u2)

    def test_reverse_receipt_action_with_reason_and_audit(self):
        """Admin can reverse a receipt via POST /api/finance/receipts/{id}/reverse/ with reason."""
        self.client.force_authenticate(user=self.admin)

        receipt = PaymentAllocationService.record_payment_with_allocations(
            receipt_data={
                "student": self.student,
                "amount": Decimal("50000.00"),
                "payer": "Emeka Okafor",
                "paid_through": "Cash",
            },
            allocations=[
                {"fee_assignment_id": self.assignment_tuition.id, "amount": Decimal("35000.00")},
                {"fee_assignment_id": self.assignment_uniform_2.id, "amount": Decimal("15000.00")},
            ],
            actor=self.admin,
        )

        self.assignment_tuition.refresh_from_db()
        self.assignment_uniform_2.refresh_from_db()
        self.assertEqual(self.assignment_tuition.amount_paid, Decimal("35000.00"))
        self.assertEqual(self.assignment_uniform_2.amount_paid, Decimal("15000.00"))

        reverse_url = f"/api/finance/receipts/{receipt.id}/reverse/"
        response = self.client.post(reverse_url, {"reason": "Customer entered wrong student"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertFalse(Receipt.objects.filter(pk=receipt.pk).exists())
        self.assignment_tuition.refresh_from_db()
        self.assignment_uniform_2.refresh_from_db()
        self.assertEqual(self.assignment_tuition.amount_paid, Decimal("0.00"))
        self.assertEqual(self.assignment_uniform_2.amount_paid, Decimal("0.00"))

        log = FinanceAuditLog.objects.filter(action=AuditAction.PAYMENT_REVERSED).last()
        self.assertIsNotNone(log)
        self.assertIn("Customer entered wrong student", log.description)
        self.assertEqual(log.metadata.get("reason"), "Customer entered wrong student")

    def test_reverse_receipt_unauthorized_for_student(self):
        """Student cannot reverse receipt (HTTP 403)."""
        receipt = PaymentAllocationService.record_payment_with_allocations(
            receipt_data={
                "student": self.student,
                "amount": Decimal("10000.00"),
                "payer": "Emeka Okafor",
                "paid_through": "Cash",
            },
            allocations=[
                {"fee_assignment_id": self.assignment_tuition.id, "amount": Decimal("10000.00")},
            ],
            actor=self.admin,
        )
        self.client.force_authenticate(user=self.student_user)
        response = self.client.post(f"/api/finance/receipts/{receipt.id}/reverse/", {"reason": "Hacking"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_student_balance_scope_includes_annual_and_repeat_charge_metadata(self):
        """Student balance endpoint includes active academic year annual fees and breakdown metadata."""
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get(f"/api/finance/student-balance/{self.student.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Total expected: 50,000 (tuition) + 20,000 (annual) + 15,000 (uniform 1) + 15,000 (uniform 2) = 100,000
        self.assertEqual(Decimal(str(data["total_fees"])), Decimal("100000.00"))

        items = data["fee_breakdown"]
        names = [i["fee_name"] for i in items]
        self.assertIn("Development Levy", names)
        self.assertIn("Tuition Fee", names)

        # Check charge_number on repeat charges
        uniform_items = [i for i in items if i["fee_name"] == "School Uniform"]
        self.assertEqual(len(uniform_items), 2)
        charge_numbers = {i["charge_number"] for i in uniform_items}
        self.assertEqual(charge_numbers, {1, 2})

    def test_parent_fees_breakdown_includes_charge_number_and_due_date(self):
        """Parent fees breakdown returns assignment_id, charge_number, and due_date."""
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.get("/api/finance/parent/fees/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        children = response.data["children_fees"]
        self.assertEqual(len(children), 1)

        breakdown = children[0]["fee_breakdown"]
        self.assertTrue(len(breakdown) >= 4)
        for item in breakdown:
            self.assertIn("assignment_id", item)
            self.assertIn("charge_number", item)
            self.assertIn("due_date", item)

    def test_receipt_serializer_exposes_allocations_and_fee_allocations(self):
        """Receipt read representation includes both allocations and fee_allocations."""
        receipt = PaymentAllocationService.record_payment_with_allocations(
            receipt_data={
                "student": self.student,
                "amount": Decimal("15000.00"),
                "payer": "Emeka Okafor",
                "paid_through": "Cash",
            },
            allocations=[
                {"fee_assignment_id": self.assignment_uniform_1.id, "amount": Decimal("15000.00")},
            ],
            actor=self.admin,
        )
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f"/api/finance/receipts/{receipt.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertIn("allocations", data)
        self.assertIn("fee_allocations", data)
        self.assertEqual(len(data["allocations"]), 1)
        self.assertEqual(len(data["fee_allocations"]), 1)
        self.assertEqual(data["allocations"][0]["fee_assignment"], self.assignment_uniform_1.id)

