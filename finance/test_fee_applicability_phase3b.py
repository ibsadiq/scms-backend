from datetime import date
from decimal import Decimal

from school.testcases import TenantTestCase

from academic.models import ClassRoom, GradeLevel, Student, StudentClassEnrollment
from administration.models import AcademicYear, Term
from finance.models import (
    FeeApplicability,
    FeeRecurrence,
    FeeStructure,
    FeeType,
    StudentFeeAssignment,
)
from finance.services import FeeAssignmentService


class FeeApplicabilityPhase3BTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        return super().setup_tenant(tenant)

    def setUp(self):
        super().setUp()

        self.year_2023 = AcademicYear.objects.create(
            name="2023/2024",
            start_date=date(2023, 9, 1),
            end_date=date(2024, 7, 31),
            active_year=False,
        )
        self.year_2025 = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            active_year=False,
        )
        self.year_2026 = AcademicYear.objects.create(
            name="2026/2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 7, 31),
            active_year=True,
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

        self.grade_1 = GradeLevel.objects.update_or_create(
            system_code="P3B_G1",
            defaults={"section": "PRIMARY", "default_name": "Grade 1", "sequence_order": 1},
        )[0]
        self.grade_2 = GradeLevel.objects.update_or_create(
            system_code="P3B_G2",
            defaults={"section": "PRIMARY", "default_name": "Grade 2", "sequence_order": 2},
        )[0]

        self.room_1a = ClassRoom.objects.create(
            name="Room 1A",
            grade_level=self.grade_1,
            capacity=35,
        )
        self.room_1b = ClassRoom.objects.create(
            name="Room 1B",
            grade_level=self.grade_1,
            capacity=35,
        )
        self.room_2a = ClassRoom.objects.create(
            name="Room 2A",
            grade_level=self.grade_2,
            capacity=35,
        )

    # =========================================================================
    # 1. Mandatory FeeStructure post-save (Signal Execution)
    # =========================================================================
    def test_mandatory_fee_structure_post_save_signal(self):
        """
        Scenario 1: Mandatory FeeStructure post-save signal.
        ONE_TIME + NEW_STUDENTS_ONLY
        New student -> assigned
        Returning student -> skipped
        """
        returning_student = Student.objects.create(
            first_name="Returning",
            last_name="Student",
            admission_number="ADM-P3B-RET",
            is_active=True,
            classroom=self.room_1a,
        )
        StudentClassEnrollment.objects.create(
            student=returning_student,
            classroom=self.room_1a,
            academic_year=self.year_2025,
            is_active=False,
        )
        StudentClassEnrollment.objects.create(
            student=returning_student,
            classroom=self.room_1a,
            academic_year=self.year_2026,
            is_active=True,
        )

        new_student = Student.objects.create(
            first_name="New",
            last_name="Student",
            admission_number="ADM-P3B-NEW",
            is_active=True,
            classroom=self.room_1a,
        )
        StudentClassEnrollment.objects.create(
            student=new_student,
            classroom=self.room_1a,
            academic_year=self.year_2026,
            is_active=True,
        )

        with self.captureOnCommitCallbacks(execute=True):
            fee = FeeStructure.objects.create(
                name="Admission Fee",
                fee_type=FeeType.ADMISSION,
                logical_fee_key="admission-fee",
                amount=Decimal("50000.00"),
                recurrence=FeeRecurrence.ONE_TIME,
                applicability=FeeApplicability.NEW_STUDENTS_ONLY,
                academic_year=self.year_2026,
                term=None,
                is_mandatory=True,
            )

        new_assigned = StudentFeeAssignment.objects.filter(
            fee_structure=fee,
            student=new_student,
        ).exists()
        ret_assigned = StudentFeeAssignment.objects.filter(
            fee_structure=fee,
            student=returning_student,
        ).exists()

        self.assertTrue(new_assigned, "New student should be assigned mandatory admission fee via signal.")
        self.assertFalse(ret_assigned, "Returning student must NOT be assigned mandatory admission fee via signal.")

    # =========================================================================
    # 2. Historical inactive/completed enrollment
    # =========================================================================
    def test_historical_inactive_enrollment_marks_as_returning(self):
        """
        Scenario 2: A student has a previous-year enrollment that is inactive/completed.
        Expected: RETURNING -> skipped for NEW_STUDENTS_ONLY.
        """
        student = Student.objects.create(
            first_name="Past",
            last_name="Inactive",
            admission_number="ADM-P3B-INACT",
            is_active=True,
            classroom=self.room_1a,
        )
        StudentClassEnrollment.objects.create(
            student=student,
            classroom=self.room_1a,
            academic_year=self.year_2025,
            is_active=False,
            notes="Completed 2025/2026 session",
        )
        enrollment_2026 = StudentClassEnrollment.objects.create(
            student=student,
            classroom=self.room_1a,
            academic_year=self.year_2026,
            is_active=True,
        )

        fee = FeeStructure.objects.create(
            name="Admission Fee",
            logical_fee_key="admission-fee",
            amount=Decimal("25000.00"),
            recurrence=FeeRecurrence.ONE_TIME,
            applicability=FeeApplicability.NEW_STUDENTS_ONLY,
            academic_year=self.year_2026,
            is_mandatory=False,
        )

        self.assertFalse(
            FeeAssignmentService.is_new_student_for_academic_year(
                student=student,
                academic_year=self.year_2026,
            )
        )
        self.assertFalse(
            FeeAssignmentService.is_student_applicable(
                student=student,
                fee_structure=fee,
                academic_year=self.year_2026,
            )
        )
        created = FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee,
            student=student,
        )
        self.assertEqual(created, 0)
        self.assertEqual(
            StudentFeeAssignment.objects.filter(student=student, fee_structure=fee).count(),
            0,
        )

    # =========================================================================
    # 3. Same-year classroom change
    # =========================================================================
    def test_same_year_classroom_change_remains_new(self):
        """
        Scenario 3: Student has multiple enrollment records in 2026/2027 (e.g. transferred class mid-year)
        but none before 2026/2027.
        Expected: NEW -> assigned for NEW_STUDENTS_ONLY.
        """
        student = Student.objects.create(
            first_name="Class",
            last_name="Transfer",
            admission_number="ADM-P3B-XFER",
            is_active=True,
            classroom=self.room_1a,
        )
        enrollment = StudentClassEnrollment.objects.create(
            student=student,
            classroom=self.room_1a,
            academic_year=self.year_2026,
            is_active=True,
        )

        # Student changes classroom mid-year within the same academic year
        enrollment.classroom = self.room_1b
        enrollment.notes = "Transferred to Room 1B mid-session"
        enrollment.save(update_fields=["classroom", "notes"])
        student.classroom = self.room_1b
        student.save(update_fields=["classroom"])

        fee = FeeStructure.objects.create(
            name="Admission Fee",
            logical_fee_key="admission-fee",
            amount=Decimal("30000.00"),
            recurrence=FeeRecurrence.ONE_TIME,
            applicability=FeeApplicability.NEW_STUDENTS_ONLY,
            academic_year=self.year_2026,
            is_mandatory=False,
        )

        self.assertTrue(
            FeeAssignmentService.is_new_student_for_academic_year(
                student=student,
                academic_year=self.year_2026,
            )
        )
        self.assertTrue(
            FeeAssignmentService.is_student_applicable(
                student=student,
                fee_structure=fee,
                academic_year=self.year_2026,
            )
        )
        created = FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee,
            student=student,
        )
        self.assertEqual(created, 1)
        self.assertEqual(
            StudentFeeAssignment.objects.filter(student=student, fee_structure=fee).count(),
            1,
        )

    # =========================================================================
    # 4. Promotion
    # =========================================================================
    def test_promotion_from_prior_year_is_returning(self):
        """
        Scenario 4: Student has 2025/2026 enrollment in Grade 1, promoted to 2026/2027 Grade 2.
        Expected: RETURNING.
        """
        student = Student.objects.create(
            first_name="Promoted",
            last_name="Kid",
            admission_number="ADM-P3B-PROM",
            is_active=True,
            classroom=self.room_2a,
        )
        StudentClassEnrollment.objects.create(
            student=student,
            classroom=self.room_1a,
            academic_year=self.year_2025,
            is_active=False,
            notes="Promoted to Grade 2",
        )
        StudentClassEnrollment.objects.create(
            student=student,
            classroom=self.room_2a,
            academic_year=self.year_2026,
            is_active=True,
        )

        fee = FeeStructure.objects.create(
            name="Admission Fee",
            logical_fee_key="admission-fee",
            amount=Decimal("20000.00"),
            recurrence=FeeRecurrence.ONE_TIME,
            applicability=FeeApplicability.NEW_STUDENTS_ONLY,
            academic_year=self.year_2026,
            is_mandatory=False,
        )

        self.assertFalse(
            FeeAssignmentService.is_new_student_for_academic_year(
                student=student,
                academic_year=self.year_2026,
            )
        )
        created = FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee,
            student=student,
        )
        self.assertEqual(created, 0)

    # =========================================================================
    # 5. Return after gap
    # =========================================================================
    def test_return_after_gap_year_is_returning(self):
        """
        Scenario 5: Student attended in 2023/2024, had a gap in 2024/2025 & 2025/2026,
        and re-enrolled in 2026/2027.
        Expected: RETURNING.
        """
        student = Student.objects.create(
            first_name="Gap",
            last_name="Returnee",
            admission_number="ADM-P3B-GAP",
            is_active=True,
            classroom=self.room_2a,
        )
        StudentClassEnrollment.objects.create(
            student=student,
            classroom=self.room_1a,
            academic_year=self.year_2023,
            is_active=False,
        )
        StudentClassEnrollment.objects.create(
            student=student,
            classroom=self.room_2a,
            academic_year=self.year_2026,
            is_active=True,
        )

        fee = FeeStructure.objects.create(
            name="Admission Fee",
            logical_fee_key="admission-fee",
            amount=Decimal("20000.00"),
            recurrence=FeeRecurrence.ONE_TIME,
            applicability=FeeApplicability.NEW_STUDENTS_ONLY,
            academic_year=self.year_2026,
            is_mandatory=False,
        )

        self.assertFalse(
            FeeAssignmentService.is_new_student_for_academic_year(
                student=student,
                academic_year=self.year_2026,
            )
        )
        created = FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee,
            student=student,
        )
        self.assertEqual(created, 0)

    # =========================================================================
    # 6. Manual auto-assign / bulk assignment
    # =========================================================================
    def test_manual_auto_assign_respects_applicability(self):
        """
        Scenario 6: Calling manual assignment / auto_assign_to_students for
        ONE_TIME + NEW_STUDENTS_ONLY must not assign returning students.
        """
        returning_student = Student.objects.create(
            first_name="ManualRet",
            last_name="Student",
            admission_number="ADM-P3B-MRET",
            is_active=True,
            classroom=self.room_1a,
        )
        StudentClassEnrollment.objects.create(
            student=returning_student,
            classroom=self.room_1a,
            academic_year=self.year_2025,
            is_active=False,
        )
        StudentClassEnrollment.objects.create(
            student=returning_student,
            classroom=self.room_1a,
            academic_year=self.year_2026,
            is_active=True,
        )

        new_student = Student.objects.create(
            first_name="ManualNew",
            last_name="Student",
            admission_number="ADM-P3B-MNEW",
            is_active=True,
            classroom=self.room_1a,
        )
        StudentClassEnrollment.objects.create(
            student=new_student,
            classroom=self.room_1a,
            academic_year=self.year_2026,
            is_active=True,
        )

        fee = FeeStructure.objects.create(
            name="Registration Fee",
            logical_fee_key="reg-fee",
            amount=Decimal("15000.00"),
            recurrence=FeeRecurrence.ONE_TIME,
            applicability=FeeApplicability.NEW_STUDENTS_ONLY,
            academic_year=self.year_2026,
            term=None,
            is_mandatory=True,
        )

        assigned_count = fee.auto_assign_to_students()
        self.assertEqual(assigned_count, 1, "Only 1 student (the new student) should be assigned.")

        self.assertTrue(
            StudentFeeAssignment.objects.filter(fee_structure=fee, student=new_student).exists()
        )
        self.assertFalse(
            StudentFeeAssignment.objects.filter(fee_structure=fee, student=returning_student).exists()
        )

    # =========================================================================
    # 7. sync_fees_for_enrollment (Dry Run and Live Run Agreement)
    # =========================================================================
    def test_sync_fees_for_enrollment_dry_run_and_live_agreement(self):
        """
        Scenario 7: Both live and dry-run eligibility decisions must agree
        and honor NEW_STUDENTS_ONLY.
        """
        returning_student = Student.objects.create(
            first_name="SyncRet",
            last_name="Student",
            admission_number="ADM-P3B-SRET",
            is_active=True,
            classroom=self.room_1a,
        )
        StudentClassEnrollment.objects.create(
            student=returning_student,
            classroom=self.room_1a,
            academic_year=self.year_2025,
            is_active=False,
        )
        ret_enrollment = StudentClassEnrollment.objects.create(
            student=returning_student,
            classroom=self.room_1a,
            academic_year=self.year_2026,
            is_active=True,
        )

        new_student = Student.objects.create(
            first_name="SyncNew",
            last_name="Student",
            admission_number="ADM-P3B-SNEW",
            is_active=True,
            classroom=self.room_1a,
        )
        new_enrollment = StudentClassEnrollment.objects.create(
            student=new_student,
            classroom=self.room_1a,
            academic_year=self.year_2026,
            is_active=True,
        )

        FeeStructure.objects.create(
            name="New Student Fee",
            logical_fee_key="new-student-fee",
            amount=Decimal("10000.00"),
            recurrence=FeeRecurrence.ONE_TIME,
            applicability=FeeApplicability.NEW_STUDENTS_ONLY,
            academic_year=self.year_2026,
            is_mandatory=True,
        )

        # Dry Run
        dry_new = FeeAssignmentService.sync_fees_for_enrollment(
            enrollment=new_enrollment,
            dry_run=True,
            return_details=True,
        )
        dry_ret = FeeAssignmentService.sync_fees_for_enrollment(
            enrollment=ret_enrollment,
            dry_run=True,
            return_details=True,
        )

        self.assertEqual(dry_new["would_create_count"], 1)
        self.assertEqual(dry_ret["would_create_count"], 0)

        # Live Run
        live_ret = FeeAssignmentService.sync_fees_for_enrollment(
            enrollment=ret_enrollment,
            dry_run=False,
            return_details=True,
        )
        live_new = FeeAssignmentService.sync_fees_for_enrollment(
            enrollment=new_enrollment,
            dry_run=False,
            return_details=True,
        )

        self.assertEqual(live_ret["created_count"], 0)
        self.assertEqual(live_new["created_count"], 1)

    # =========================================================================
    # 8. ALL_ELIGIBLE regression
    # =========================================================================
    def test_all_eligible_one_time_fee_applies_to_both_new_and_returning(self):
        """
        Scenario 8: ONE_TIME + ALL_ELIGIBLE behaves according to lifetime recurrence
        and is NOT filtered out by new-student logic.
        """
        returning_student = Student.objects.create(
            first_name="AllEligRet",
            last_name="Student",
            admission_number="ADM-P3B-AERET",
            is_active=True,
            classroom=self.room_1a,
        )
        StudentClassEnrollment.objects.create(
            student=returning_student,
            classroom=self.room_1a,
            academic_year=self.year_2025,
            is_active=False,
        )
        StudentClassEnrollment.objects.create(
            student=returning_student,
            classroom=self.room_1a,
            academic_year=self.year_2026,
            is_active=True,
        )

        new_student = Student.objects.create(
            first_name="AllEligNew",
            last_name="Student",
            admission_number="ADM-P3B-AENEW",
            is_active=True,
            classroom=self.room_1a,
        )
        StudentClassEnrollment.objects.create(
            student=new_student,
            classroom=self.room_1a,
            academic_year=self.year_2026,
            is_active=True,
        )

        fee = FeeStructure.objects.create(
            name="Development Levy",
            logical_fee_key="dev-levy",
            amount=Decimal("40000.00"),
            recurrence=FeeRecurrence.ONE_TIME,
            applicability=FeeApplicability.ALL_ELIGIBLE,
            academic_year=self.year_2026,
            is_mandatory=True,
        )

        assigned_count = fee.auto_assign_to_students()
        self.assertEqual(assigned_count, 2, "Both students should be assigned the ALL_ELIGIBLE one-time fee.")

    # =========================================================================
    # 9. PER_TERM behavior regression
    # =========================================================================
    def test_per_term_all_eligible_remains_unchanged(self):
        """
        Scenario 9: Existing PER_TERM + ALL_ELIGIBLE behavior must remain unchanged.
        """
        student = Student.objects.create(
            first_name="PerTerm",
            last_name="Student",
            admission_number="ADM-P3B-PT",
            is_active=True,
            classroom=self.room_1a,
        )
        StudentClassEnrollment.objects.create(
            student=student,
            classroom=self.room_1a,
            academic_year=self.year_2026,
            is_active=True,
        )

        fee = FeeStructure.objects.create(
            name="Tuition Fee",
            fee_type=FeeType.TUITION,
            logical_fee_key="tuition-fee",
            amount=Decimal("60000.00"),
            recurrence=FeeRecurrence.PER_TERM,
            applicability=FeeApplicability.ALL_ELIGIBLE,
            academic_year=self.year_2026,
            term=self.term_2026_t1,
            is_mandatory=True,
        )

        self.assertTrue(fee.applies_to_student(student, self.term_2026_t1))
        created = FeeAssignmentService.assign_fee_to_student(
            fee_structure=fee,
            student=student,
            term=self.term_2026_t1,
        )
        self.assertEqual(created, 1)
