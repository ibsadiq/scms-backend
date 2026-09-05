from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from school.testcases import TenantTestCase

from academic.models import ClassRoom, GradeLevel, Student, StudentClassEnrollment
from administration.models import AcademicYear, Term
from finance.models import (
    FeeApplicability,
    FeeRecurrence,
    FeeStructure,
    StudentFeeAssignment,
)
from finance.serializers import FeeStructureSerializer

User = get_user_model()


class FeeRecurrencePhase1Tests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        return super().setup_tenant(tenant)

    def setUp(self):
        super().setUp()
        self.year = AcademicYear.objects.create(
            name="2026/2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 7, 31),
            active_year=True,
        )
        self.term = Term.objects.create(
            name="First Term",
            academic_year=self.year,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 15),
        )
        self.grade = GradeLevel.objects.update_or_create(
            system_code="PHASE1_G1",
            defaults={"section": "PRIMARY", "default_name": "Grade 1", "sequence_order": 1},
        )[0]
        self.classroom = ClassRoom.objects.create(
            name="Phase 1 Class",
            grade_level=self.grade,
            capacity=30,
        )
        self.student = Student.objects.create(
            first_name="Alan",
            last_name="Turing",
            admission_number="ADM-P1-001",
            parent_contact="08012345678",
            is_active=True,
        )
        self.enrollment = StudentClassEnrollment.objects.create(
            student=self.student,
            classroom=self.classroom,
            academic_year=self.year,
            is_active=True,
        )
        self.accountant = User.objects.create_user(
            email="accountant-phase1@test.local",
            password="password123",
            is_accountant=True,
        )

    def test_01_legacy_feestructure_creation_defaults(self):
        """1. Legacy FeeStructure creation gives default recurrence, applicability, and blank logical_fee_key."""
        fee = FeeStructure.objects.create(
            name="Default Tuition",
            amount=Decimal("45000.00"),
            academic_year=self.year,
            term=self.term,
        )
        self.assertEqual(fee.logical_fee_key, "")
        self.assertEqual(fee.recurrence, FeeRecurrence.PER_TERM)
        self.assertEqual(fee.applicability, FeeApplicability.ALL_ELIGIBLE)

    def test_02_explicit_values_can_be_stored_on_feestructure(self):
        """2. Explicit values can be stored: logical_fee_key, ONE_TIME, NEW_STUDENTS_ONLY."""
        fee = FeeStructure.objects.create(
            name="Admission Fee",
            amount=Decimal("25000.00"),
            academic_year=self.year,
            term=self.term,
            logical_fee_key="admission-fee",
            recurrence=FeeRecurrence.ONE_TIME,
            applicability=FeeApplicability.NEW_STUDENTS_ONLY,
        )
        fee.refresh_from_db()
        self.assertEqual(fee.logical_fee_key, "admission-fee")
        self.assertEqual(fee.recurrence, FeeRecurrence.ONE_TIME)
        self.assertEqual(fee.applicability, FeeApplicability.NEW_STUDENTS_ONLY)

    def test_03_annual_recurrence_can_be_stored(self):
        """3. ANNUAL can be stored."""
        fee = FeeStructure.objects.create(
            name="Development Levy",
            amount=Decimal("15000.00"),
            academic_year=self.year,
            term=self.term,
            recurrence=FeeRecurrence.ANNUAL,
        )
        fee.refresh_from_db()
        self.assertEqual(fee.recurrence, FeeRecurrence.ANNUAL)

    def test_04_legacy_studentfeeassignment_creation_defaults(self):
        """4. Legacy StudentFeeAssignment creation remains valid with blank key, PER_TERM, and None academic_year."""
        fee = FeeStructure.objects.create(
            name="Standard Term Fee",
            amount=Decimal("30000.00"),
            academic_year=self.year,
            term=self.term,
        )
        assignment = StudentFeeAssignment.objects.create(
            student=self.student,
            fee_structure=fee,
            term=self.term,
            amount_owed=Decimal("30000.00"),
        )
        assignment.refresh_from_db()
        self.assertEqual(assignment.logical_fee_key, "")
        self.assertEqual(assignment.recurrence, FeeRecurrence.PER_TERM)
        self.assertIsNone(assignment.academic_year)

    def test_04b_explicit_studentfeeassignment_metadata_stored(self):
        """4b. Explicit metadata can be stored on StudentFeeAssignment if supplied."""
        student2 = Student.objects.create(
            first_name="Ada",
            last_name="Lovelace",
            admission_number="ADM-P1-002",
            parent_contact="08087654321",
            is_active=True,
        )
        fee = FeeStructure.objects.create(
            name="One-Time Matriculation",
            amount=Decimal("20000.00"),
            academic_year=self.year,
            logical_fee_key="matriculation-fee",
            recurrence=FeeRecurrence.ONE_TIME,
        )
        assignment = StudentFeeAssignment.objects.create(
            student=student2,
            fee_structure=fee,
            term=self.term,
            amount_owed=Decimal("20000.00"),
            logical_fee_key="matriculation-fee",
            recurrence=FeeRecurrence.ONE_TIME,
            academic_year=self.year,
        )
        assignment.refresh_from_db()
        self.assertEqual(assignment.logical_fee_key, "matriculation-fee")
        self.assertEqual(assignment.recurrence, FeeRecurrence.ONE_TIME)
        self.assertEqual(assignment.academic_year, self.year)

    def test_05_existing_student_fee_term_uniqueness_protection_unchanged(self):
        """5. Existing (student, fee_structure, term) uniqueness protection remains unchanged."""
        fee = FeeStructure.objects.create(
            name="Tuition Fee Unique",
            amount=Decimal("50000.00"),
            academic_year=self.year,
            term=self.term,
        )
        StudentFeeAssignment.objects.create(
            student=self.student,
            fee_structure=fee,
            term=self.term,
            amount_owed=Decimal("50000.00"),
        )
        with self.assertRaises(IntegrityError):
            StudentFeeAssignment.objects.create(
                student=self.student,
                fee_structure=fee,
                term=self.term,
                amount_owed=Decimal("50000.00"),
            )

    def test_06_existing_api_payload_omitting_new_fields_remains_valid(self):
        """6. Existing API payloads that omit the new FeeStructure fields remain valid."""
        payload = {
            "name": "Legacy Exam Fee",
            "fee_type": "Exam",
            "amount": "5000.00",
            "academic_year": self.year.pk,
            "term": self.term.pk,
            "is_mandatory": True,
        }
        serializer = FeeStructureSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        fee = serializer.save(created_by=self.accountant)

        self.assertEqual(fee.logical_fee_key, "")
        self.assertEqual(fee.recurrence, FeeRecurrence.PER_TERM)
        self.assertEqual(fee.applicability, FeeApplicability.ALL_ELIGIBLE)
