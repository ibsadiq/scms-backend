from datetime import date
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from school.testcases import TenantTestCase

from academic.models import ClassRoom, GradeLevel, Student, StudentClassEnrollment
from administration.models import AcademicYear, Term
from finance.models import (
    FeeStructure,
    FeeType,
    OptionalService,
    ServiceSubscription,
    StudentFeeAssignment,
)


class SyncEnrollmentFeesCommandTests(TenantTestCase):
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
        self.grade_1 = GradeLevel.objects.update_or_create(
            system_code="GRADE_1",
            defaults={"section": "PRIMARY", "default_name": "Grade 1", "sequence_order": 1},
        )[0]
        self.grade_2 = GradeLevel.objects.update_or_create(
            system_code="GRADE_2",
            defaults={"section": "PRIMARY", "default_name": "Grade 2", "sequence_order": 2},
        )[0]
        self.classroom_1 = ClassRoom.objects.create(
            name="Primary 1A",
            grade_level=self.grade_1,
            capacity=30,
        )
        self.classroom_2 = ClassRoom.objects.create(
            name="Primary 2A",
            grade_level=self.grade_2,
            capacity=30,
        )
        self.student_1 = Student.objects.create(
            first_name="Ada",
            last_name="Lovelace",
            admission_number="ADM-2026-001",
            parent_contact="08011111111",
            is_active=True,
        )
        self.student_2 = Student.objects.create(
            first_name="Charles",
            last_name="Babbage",
            admission_number="ADM-2026-002",
            parent_contact="08022222222",
            is_active=True,
        )
        self.enrollment_1 = StudentClassEnrollment.objects.create(
            student=self.student_1,
            classroom=self.classroom_1,
            academic_year=self.year,
            is_active=True,
        )
        self.enrollment_2 = StudentClassEnrollment.objects.create(
            student=self.student_2,
            classroom=self.classroom_2,
            academic_year=self.year,
            is_active=True,
        )
        self.mandatory_fee = FeeStructure.objects.create(
            name="General Tuition",
            amount=Decimal("50000.00"),
            academic_year=self.year,
            term=self.term,
            is_mandatory=True,
        )

    def test_dry_run_creates_nothing(self):
        """--dry-run must perform zero database writes and report would-be created count."""
        out = StringIO()
        call_command(
            "sync_enrollment_fees",
            academic_year="2026/2027",
            dry_run=True,
            stdout=out,
        )
        output = out.getvalue()
        self.assertEqual(StudentFeeAssignment.objects.count(), 0)
        self.assertIn("DRY RUN (zero database writes)", output)
        self.assertIn("Assignments that would be created: 2", output)
        self.assertIn("Assignments created:               0", output)

    def test_real_run_creates_missing_applicable_assignments(self):
        """Real run creates missing applicable assignments for active enrollments."""
        out = StringIO()
        call_command(
            "sync_enrollment_fees",
            academic_year="2026/2027",
            stdout=out,
        )
        output = out.getvalue()
        self.assertEqual(StudentFeeAssignment.objects.count(), 2)
        assignment_1 = StudentFeeAssignment.objects.get(student=self.student_1, fee_structure=self.mandatory_fee)
        self.assertEqual(assignment_1.amount_owed, Decimal("50000.00"))
        self.assertEqual(assignment_1.amount_paid, Decimal("0.00"))
        self.assertFalse(assignment_1.is_waived)
        self.assertIn("Assignments created:               2", output)

    def test_second_run_creates_no_duplicates(self):
        """Command is strictly idempotent; re-running produces no duplicate records."""
        # First run
        call_command("sync_enrollment_fees", academic_year="2026/2027")
        self.assertEqual(StudentFeeAssignment.objects.count(), 2)

        # Second run
        out = StringIO()
        call_command("sync_enrollment_fees", academic_year="2026/2027", stdout=out)
        output = out.getvalue()
        self.assertEqual(StudentFeeAssignment.objects.count(), 2)
        self.assertIn("Assignments created:               0", output)
        self.assertIn("Assignments already existing:      2", output)

    def test_previous_year_fees_excluded(self):
        """Strict academic-year isolation: previous year fees must never be assigned."""
        prev_year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            active_year=False,
        )
        prev_term = Term.objects.create(
            name="First Term",
            academic_year=prev_year,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
        )
        prev_fee = FeeStructure.objects.create(
            name="Old Year Fee",
            amount=Decimal("30000.00"),
            academic_year=prev_year,
            term=prev_term,
            is_mandatory=True,
        )

        call_command("sync_enrollment_fees", academic_year="2026/2027")

        # Current fee is assigned, previous year fee is NOT assigned
        self.assertTrue(
            StudentFeeAssignment.objects.filter(
                student=self.student_1, fee_structure=self.mandatory_fee
            ).exists()
        )
        self.assertFalse(
            StudentFeeAssignment.objects.filter(
                student=self.student_1, fee_structure=prev_fee
            ).exists()
        )

    def test_existing_paid_assignment_preserved(self):
        """Existing amount_paid must never be overwritten, reset, or modified."""
        existing_assignment = StudentFeeAssignment.objects.create(
            student=self.student_1,
            fee_structure=self.mandatory_fee,
            term=self.term,
            amount_owed=Decimal("50000.00"),
            amount_paid=Decimal("25000.00"),
        )

        call_command("sync_enrollment_fees", academic_year="2026/2027")

        existing_assignment.refresh_from_db()
        self.assertEqual(existing_assignment.amount_paid, Decimal("25000.00"))
        self.assertEqual(existing_assignment.amount_owed, Decimal("50000.00"))

    def test_existing_waived_assignment_preserved(self):
        """Existing is_waived and waiver reasons must never be touched."""
        existing_assignment = StudentFeeAssignment.objects.create(
            student=self.student_1,
            fee_structure=self.mandatory_fee,
            term=self.term,
            amount_owed=Decimal("50000.00"),
            amount_paid=Decimal("0.00"),
            is_waived=True,
            waived_reason="Merit Scholarship 2026",
        )

        call_command("sync_enrollment_fees", academic_year="2026/2027")

        existing_assignment.refresh_from_db()
        self.assertTrue(existing_assignment.is_waived)
        self.assertEqual(existing_assignment.waived_reason, "Merit Scholarship 2026")

    def test_classroom_scoped_applicability(self):
        """Fee scoped to specific classroom applies only to students enrolled in that classroom."""
        classroom_fee = FeeStructure.objects.create(
            name="Primary 1 Lab Fee",
            amount=Decimal("5000.00"),
            academic_year=self.year,
            term=self.term,
            is_mandatory=True,
        )
        classroom_fee.classrooms.add(self.classroom_1)

        call_command("sync_enrollment_fees", academic_year="2026/2027")

        # Student 1 is in Primary 1A -> gets classroom fee
        self.assertTrue(
            StudentFeeAssignment.objects.filter(
                student=self.student_1, fee_structure=classroom_fee
            ).exists()
        )
        # Student 2 is in Primary 2A -> does NOT get classroom fee
        self.assertFalse(
            StudentFeeAssignment.objects.filter(
                student=self.student_2, fee_structure=classroom_fee
            ).exists()
        )

    def test_grade_level_scoped_applicability(self):
        """Fee scoped to grade level applies only to students in classrooms belonging to that grade level."""
        grade_fee = FeeStructure.objects.create(
            name="Grade 1 Special Fee",
            amount=Decimal("7000.00"),
            academic_year=self.year,
            term=self.term,
            is_mandatory=True,
        )
        grade_fee.grade_levels.add(self.grade_1)

        call_command("sync_enrollment_fees", academic_year="2026/2027")

        # Student 1 is in Grade 1 -> gets grade fee
        self.assertTrue(
            StudentFeeAssignment.objects.filter(
                student=self.student_1, fee_structure=grade_fee
            ).exists()
        )
        # Student 2 is in Grade 2 -> does NOT get grade fee
        self.assertFalse(
            StudentFeeAssignment.objects.filter(
                student=self.student_2, fee_structure=grade_fee
            ).exists()
        )

    def test_optional_fee_behavior_preserved(self):
        """Optional fee is assigned only to students actively subscribed to that service."""
        bus_service = OptionalService.objects.create(
            name="School Bus Route A",
            fee_type=FeeType.TRANSPORT,
            is_active=True,
        )
        optional_fee = FeeStructure.objects.create(
            name="Bus Transport Fee",
            amount=Decimal("15000.00"),
            academic_year=self.year,
            term=self.term,
            is_mandatory=False,
            optional_service=bus_service,
        )

        # Only student 1 subscribes
        ServiceSubscription.objects.create(
            student=self.student_1,
            service=bus_service,
            is_active=True,
        )

        call_command("sync_enrollment_fees", academic_year="2026/2027")

        # Subscribed student gets optional fee
        self.assertTrue(
            StudentFeeAssignment.objects.filter(
                student=self.student_1, fee_structure=optional_fee
            ).exists()
        )
        # Unsubscribed student does NOT get optional fee
        self.assertFalse(
            StudentFeeAssignment.objects.filter(
                student=self.student_2, fee_structure=optional_fee
            ).exists()
        )

    def test_student_id_filter(self):
        """--student-id limits processing strictly to the specified student."""
        out = StringIO()
        call_command(
            "sync_enrollment_fees",
            academic_year="2026/2027",
            student_id=self.student_1.admission_number,
            stdout=out,
        )
        output = out.getvalue()
        self.assertIn("Enrollments scanned:               1", output)
        self.assertTrue(
            StudentFeeAssignment.objects.filter(
                student=self.student_1, fee_structure=self.mandatory_fee
            ).exists()
        )
        self.assertFalse(
            StudentFeeAssignment.objects.filter(
                student=self.student_2, fee_structure=self.mandatory_fee
            ).exists()
        )

    def test_classroom_id_filter(self):
        """--classroom-id limits processing strictly to students in that classroom."""
        out = StringIO()
        call_command(
            "sync_enrollment_fees",
            academic_year="2026/2027",
            classroom_id=self.classroom_1.name,
            stdout=out,
        )
        output = out.getvalue()
        self.assertIn("Enrollments scanned:               1", output)
        self.assertTrue(
            StudentFeeAssignment.objects.filter(
                student=self.student_1, fee_structure=self.mandatory_fee
            ).exists()
        )
        self.assertFalse(
            StudentFeeAssignment.objects.filter(
                student=self.student_2, fee_structure=self.mandatory_fee
            ).exists()
        )

    def test_academic_year_filter(self):
        """--academic-year targets only enrollments and fees for the specified year."""
        year_2 = AcademicYear.objects.create(
            name="2027/2028",
            start_date=date(2027, 9, 1),
            end_date=date(2028, 7, 31),
            active_year=False,
        )
        term_2 = Term.objects.create(
            name="First Term",
            academic_year=year_2,
            start_date=date(2027, 9, 1),
            end_date=date(2027, 12, 15),
        )
        fee_year_2 = FeeStructure.objects.create(
            name="Tuition 2027/2028",
            amount=Decimal("60000.00"),
            academic_year=year_2,
            term=term_2,
            is_mandatory=True,
        )
        student_3 = Student.objects.create(
            first_name="Grace",
            last_name="Hopper",
            admission_number="ADM-2027-001",
            parent_contact="08033333333",
            is_active=True,
        )
        StudentClassEnrollment.objects.create(
            student=student_3,
            classroom=self.classroom_1,
            academic_year=year_2,
            is_active=True,
        )

        out = StringIO()
        call_command(
            "sync_enrollment_fees",
            academic_year="2026/2027",
            stdout=out,
        )
        output = out.getvalue()
        self.assertIn("Academic Year: 2026/2027", output)
        self.assertIn("Enrollments scanned:               2", output)
        # Year 1 students got Year 1 fee
        self.assertTrue(
            StudentFeeAssignment.objects.filter(
                student=self.student_1, fee_structure=self.mandatory_fee
            ).exists()
        )
        # Year 2 student was not touched
        self.assertFalse(
            StudentFeeAssignment.objects.filter(
                student=student_3, fee_structure=fee_year_2
            ).exists()
        )

    def test_explicit_schema_argument(self):
        """Command executes cleanly when --schema is explicitly provided."""
        out = StringIO()
        call_command(
            "sync_enrollment_fees",
            schema=self.tenant.schema_name,
            academic_year="2026/2027",
            stdout=out,
        )
        self.assertEqual(StudentFeeAssignment.objects.count(), 2)

    def test_invalid_schema_raises_error(self):
        """Invalid schema name raises CommandError."""
        with self.assertRaises(CommandError) as ctx:
            call_command(
                "sync_enrollment_fees",
                schema="non_existent_tenant_schema_xyz",
                academic_year="2026/2027",
            )
        self.assertIn("does not exist", str(ctx.exception))
