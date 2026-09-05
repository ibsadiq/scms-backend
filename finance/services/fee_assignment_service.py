from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q

from academic.models import Student
from administration.models import Term
from finance.models import (
    FeeApplicability,
    FeeRecurrence,
    FeeStructure,
    ServiceSubscription,
    StudentFeeAssignment,
)


class FeeAssignmentService:
    @classmethod
    def _validate_recurrence_logical_key(cls, fee_structure):
        """
        Ensures FeeStructures configured with ANNUAL or ONE_TIME recurrence
        have a valid, non-blank logical_fee_key.
        Legacy PER_TERM allows blank keys for backward compatibility.
        """
        if fee_structure.recurrence in (FeeRecurrence.ANNUAL, FeeRecurrence.ONE_TIME):
            key = fee_structure.logical_fee_key
            if not key or not str(key).strip():
                raise ValidationError(
                    f"FeeStructure '{fee_structure.name}' (ID {fee_structure.pk}) has recurrence "
                    f"'{fee_structure.recurrence}' but logical_fee_key is blank. "
                    "Cannot safely establish recurrence identity."
                )

    @classmethod
    def _resolve_target_term(cls, fee_structure, context_term=None):
        """
        Resolves the appropriate Term for assigning a FeeStructure.

        - If fee_structure.term_id is set:
            - If context_term is provided and context_term.pk != fee_structure.term_id:
                Returns None (fee is explicitly configured for another term).
            - Otherwise returns fee_structure.term.
        - If fee_structure.term_id is None:
            - If context_term is provided: returns context_term.
            - Otherwise resolves effective term for fee_structure.academic_year.
        """
        if fee_structure.term_id:
            if context_term and context_term.pk != fee_structure.term_id:
                return None
            return fee_structure.term

        if context_term:
            return context_term

        return cls.resolve_effective_term(fee_structure.academic_year)

    @classmethod
    def find_existing_obligation(cls, *, student, fee_structure, term=None):
        """
        Queries whether a financial obligation already exists for the given student
        under the fee_structure's recurrence policy.

        - ONE_TIME: Spans all academic years, terms, and FeeStructure rows for (student, logical_fee_key).
        - ANNUAL: Spans all terms in fee_structure.academic_year for (student, logical_fee_key).
        - PER_TERM: Spans (student, fee_structure, term).

        Returns:
            Existing StudentFeeAssignment instance if found, else None.
        """
        cls._validate_recurrence_logical_key(fee_structure)

        recurrence = fee_structure.recurrence
        logical_key = fee_structure.logical_fee_key

        if recurrence == FeeRecurrence.ONE_TIME:
            assignment = StudentFeeAssignment.objects.filter(
                student=student,
                logical_fee_key=logical_key,
                recurrence=FeeRecurrence.ONE_TIME,
            ).first()
            if assignment is not None:
                return assignment
            # Legacy fallback: check exact (student, fee_structure, term) if term is known
            if term is not None:
                return StudentFeeAssignment.objects.filter(
                    student=student,
                    fee_structure=fee_structure,
                    term=term,
                ).first()
            return None

        elif recurrence == FeeRecurrence.ANNUAL:
            assignment = StudentFeeAssignment.objects.filter(
                student=student,
                logical_fee_key=logical_key,
                academic_year=fee_structure.academic_year,
                recurrence=FeeRecurrence.ANNUAL,
            ).first()
            if assignment is not None:
                return assignment
            # Legacy fallback: check exact (student, fee_structure, term) if term is known
            if term is not None:
                return StudentFeeAssignment.objects.filter(
                    student=student,
                    fee_structure=fee_structure,
                    term=term,
                ).first()
            return None

        else:  # PER_TERM
            if term is None:
                return None
            return StudentFeeAssignment.objects.filter(
                student=student,
                fee_structure=fee_structure,
                term=term,
            ).first()

    @classmethod
    def resolve_assignment_financials(cls, *, fee_structure, target_term):
        """
        Resolves the authoritative (amount, due_date) tuple for creating an assignment.

        - ANNUAL / ONE_TIME:
            Returns (fee_structure.amount, fee_structure.due_date)
        - PER_TERM with specific term (fee_structure.term is not None):
            Returns (fee_structure.amount, fee_structure.due_date)
        - PER_TERM with All Terms (fee_structure.term is None):
            Requires a matching FeeTermSchedule for target_term.
            If missing, raises ValidationError.
            If found:
                amount = schedule.amount if schedule.amount is not None else fee_structure.amount
                due_date = schedule.due_date
        """
        if fee_structure.recurrence in (FeeRecurrence.ANNUAL, FeeRecurrence.ONE_TIME):
            return fee_structure.amount, fee_structure.due_date

        # PER_TERM + specific term
        if fee_structure.term_id is not None:
            return fee_structure.amount, fee_structure.due_date

        # PER_TERM + All Terms
        if not target_term:
            raise ValidationError(
                f"Target term is required to resolve fee schedule for '{fee_structure.name}' (ID {fee_structure.pk})."
            )

        from finance.models import FeeTermSchedule
        try:
            schedule = FeeTermSchedule.objects.get(
                fee_structure=fee_structure,
                term=target_term,
            )
        except FeeTermSchedule.DoesNotExist:
            term_name = getattr(target_term, "name", str(target_term))
            raise ValidationError(
                f'No fee term schedule is configured for "{term_name}".'
            )

        amount = schedule.amount if schedule.amount is not None else fee_structure.amount
        due_date = schedule.due_date
        return amount, due_date

    @classmethod
    def _create_assignment_with_snapshot(cls, *, student, fee_structure, target_term):
        """
        Creates a new StudentFeeAssignment capturing immutable metadata snapshots.
        Handles concurrent insertion races safely by catching IntegrityError,
        retrieving the winning transaction's assignment via find_existing_obligation,
        and returning (assignment, False).
        Re-raises any unrelated IntegrityError.
        """
        cls._validate_recurrence_logical_key(fee_structure)
        resolved_amount, resolved_due_date = cls.resolve_assignment_financials(
            fee_structure=fee_structure,
            target_term=target_term,
        )

        try:
            with transaction.atomic():
                assignment = StudentFeeAssignment.objects.create(
                    student=student,
                    fee_structure=fee_structure,
                    term=target_term,
                    amount_owed=resolved_amount,
                    amount_paid=Decimal("0.00"),
                    due_date=resolved_due_date,
                    logical_fee_key=fee_structure.logical_fee_key,
                    recurrence=fee_structure.recurrence,
                    academic_year=fee_structure.academic_year,
                )
                return assignment, True
        except IntegrityError:
            existing = cls.find_existing_obligation(
                student=student,
                fee_structure=fee_structure,
                term=target_term,
            )
            if existing is not None:
                return existing, False
            raise

    @classmethod
    def get_or_create_assignment(cls, *, fee_structure, student, term=None):
        """
        Recurrence-aware get_or_create for StudentFeeAssignment.
        Returns:
            (assignment, created: bool)
        """
        target_term = cls._resolve_target_term(fee_structure, context_term=term)
        if not target_term:
            raise ValidationError(
                f"Cannot resolve target term for FeeStructure '{fee_structure.name}' (ID {fee_structure.pk})."
            )

        existing = cls.find_existing_obligation(
            student=student,
            fee_structure=fee_structure,
            term=target_term,
        )
        if existing is not None:
            return existing, False

        return cls._create_assignment_with_snapshot(
            student=student,
            fee_structure=fee_structure,
            target_term=target_term,
        )

    @classmethod
    def is_new_student_for_academic_year(cls, *, student, academic_year):
        """
        Determines whether a student is NEW for the given academic year.
        Phase 3B rule:
        A student is NEW for academic year Y iff there is no historical StudentClassEnrollment
        for that student belonging to an academic year whose:
            academic_year.start_date < Y.start_date

        A previous enrollment in any earlier academic year means RETURNING, including:
        - promoted students
        - repeaters
        - students returning after a gap
        - students whose old enrollment is inactive/completed/promoted
        - students changing classrooms in later years

        Same-year classroom changes do NOT make the student returning.
        """
        if not student or not academic_year or not academic_year.start_date:
            return True

        from academic.models import StudentClassEnrollment

        has_prior_enrollment = StudentClassEnrollment.objects.filter(
            student=student,
            academic_year__start_date__lt=academic_year.start_date,
        ).exists()
        return not has_prior_enrollment

    @classmethod
    def is_student_applicable(cls, *, student, fee_structure, academic_year=None, term=None):
        """
        Authoritative check for whether a FeeStructure is applicable to a student.
        Evaluates:
        1. Structural scope: grade_levels
        2. Structural scope: classrooms
        3. Structural scope: term
        4. Applicability policy: FeeApplicability (ALL_ELIGIBLE vs NEW_STUDENTS_ONLY)
        """
        target_year = academic_year or fee_structure.academic_year

        # 1. Check grade levels
        grade_levels_list = list(fee_structure.grade_levels.all())
        if grade_levels_list:
            student_grade = (
                student.classroom.grade_level
                if (student.classroom and hasattr(student.classroom, "grade_level"))
                else None
            )
            if not student_grade or student_grade not in grade_levels_list:
                return False

        # 2. Check classrooms
        classrooms_list = list(fee_structure.classrooms.all())
        if classrooms_list:
            if not student.classroom or student.classroom not in classrooms_list:
                return False

        # 3. Check term
        if fee_structure.term_id and term:
            term_id = term.pk if hasattr(term, "pk") else term
            if fee_structure.term_id != term_id:
                return False

        # 4. Check applicability policy (Phase 3B)
        if fee_structure.applicability == FeeApplicability.NEW_STUDENTS_ONLY:
            if not cls.is_new_student_for_academic_year(
                student=student,
                academic_year=target_year,
            ):
                return False

        return True

    @classmethod
    def assign_fee(cls, *, fee_structure, term=None):
        if not fee_structure.is_mandatory and not fee_structure.optional_service_id:
            return 0
        students = Student.objects.filter(is_active=True)
        if not fee_structure.is_mandatory:
            students = students.filter(
                id__in=ServiceSubscription.objects.filter(
                    service=fee_structure.optional_service, is_active=True
                ).values_list("student_id", flat=True)
            )
        grade_levels = list(fee_structure.grade_levels.all())
        classrooms = list(fee_structure.classrooms.all())
        if grade_levels:
            students = students.filter(classroom__grade_level__in=grade_levels)
        if classrooms:
            students = students.filter(classroom__in=classrooms)

        if fee_structure.term_id:
            terms = [fee_structure.term]
        elif term:
            terms = [term]
        elif fee_structure.recurrence == FeeRecurrence.PER_TERM:
            scheduled_terms = list(
                Term.objects.filter(
                    fee_term_schedules__fee_structure=fee_structure
                ).order_by("start_date")
            )
            if not scheduled_terms:
                raise ValidationError(
                    f'No fee term schedule is configured for fee structure "{fee_structure.name}" (ID {fee_structure.pk}).'
                )
            terms = scheduled_terms
        else:
            terms = list(
                Term.objects.filter(academic_year=fee_structure.academic_year).order_by("start_date")[:1]
            )

        created_count = 0
        for student in students.iterator(chunk_size=500):
            for assignment_term in terms:
                if not assignment_term or not cls.is_student_applicable(
                    student=student,
                    fee_structure=fee_structure,
                    academic_year=fee_structure.academic_year,
                    term=assignment_term,
                ):
                    continue
                created = cls.assign_fee_to_student(
                    fee_structure=fee_structure,
                    student=student,
                    term=assignment_term,
                )
                created_count += created
        return created_count

    @classmethod
    def assign_current_fees_to_student(cls, *, student, term):
        assigned = 0
        fees = FeeStructure.objects.filter(
            is_mandatory=True, academic_year=term.academic_year
        )
        for fee in fees:
            if cls.is_student_applicable(
                student=student,
                fee_structure=fee,
                academic_year=term.academic_year,
                term=term,
            ):
                assigned += cls.assign_fee_to_student(
                    fee_structure=fee, student=student, term=term
                )
        return assigned

    @classmethod
    def assign_fee_to_student(cls, *, fee_structure, student, term=None):
        """
        Assigns fee_structure to student under recurrence policy.
        Preserves existing contract: returns 1 if newly created, 0 if already existed or not assignable.
        """
        target_term = cls._resolve_target_term(fee_structure, context_term=term)
        if not target_term:
            return 0

        if not cls.is_student_applicable(
            student=student,
            fee_structure=fee_structure,
            academic_year=fee_structure.academic_year,
            term=target_term,
        ):
            return 0

        existing = cls.find_existing_obligation(
            student=student,
            fee_structure=fee_structure,
            term=target_term,
        )
        if existing is not None:
            return 0

        _, created = cls._create_assignment_with_snapshot(
            student=student,
            fee_structure=fee_structure,
            target_term=target_term,
        )
        return int(created)

    @classmethod
    def resolve_effective_term(cls, academic_year):
        """
        Resolves the authoritative Term for a given AcademicYear.
        Works seamlessly before, during, and after term dates.
        """
        if not academic_year:
            return None
        from django.utils import timezone
        today = timezone.localdate()

        # 1. Active term encompassing today
        term = Term.objects.filter(
            academic_year=academic_year,
            start_date__lte=today,
            end_date__gte=today,
        ).order_by("start_date").first()
        if term:
            return term

        # 2. Upcoming term in this academic year (pre-session / onboarding)
        term = Term.objects.filter(
            academic_year=academic_year,
            start_date__gt=today,
        ).order_by("start_date").first()
        if term:
            return term

        # 3. Most recent completed term in this academic year
        term = Term.objects.filter(
            academic_year=academic_year,
            end_date__lt=today,
        ).order_by("-end_date").first()
        if term:
            return term

        # 4. Fallback: First term ordered by start_date or pk
        return Term.objects.filter(
            academic_year=academic_year,
        ).order_by("start_date", "pk").first()

    @classmethod
    def sync_fees_for_enrollment(
        cls,
        *,
        enrollment,
        term=None,
        dry_run=False,
        return_details=False,
    ):
        """
        Authoritative fee synchronization for an active student enrollment.
        Uses enrollment.student, enrollment.classroom, and enrollment.academic_year.
        Works before, during, and after term commencement dates.
        Strictly confines fee assignments to enrollment.academic_year.
        Enforces recurrence rules (PER_TERM, ANNUAL, ONE_TIME) centrally.
        """
        if not enrollment or not enrollment.is_active:
            if return_details:
                return {
                    "applicable_count": 0,
                    "created_count": 0,
                    "existing_count": 0,
                    "would_create_count": 0,
                    "skipped": True,
                    "skip_reason": "Enrollment is inactive or missing",
                    "errors": [],
                }
            return 0

        student = enrollment.student
        classroom = enrollment.classroom
        academic_year = enrollment.academic_year

        if not student or not student.is_active or not classroom or not academic_year:
            if return_details:
                return {
                    "applicable_count": 0,
                    "created_count": 0,
                    "existing_count": 0,
                    "would_create_count": 0,
                    "skipped": True,
                    "skip_reason": "Student is inactive or missing classroom/academic_year",
                    "errors": [],
                }
            return 0

        # Ensure student snapshot has classroom set in-memory for applies_to_student checks
        student.classroom = classroom

        effective_term = term or cls.resolve_effective_term(academic_year)
        if not effective_term:
            if return_details:
                return {
                    "applicable_count": 0,
                    "created_count": 0,
                    "existing_count": 0,
                    "would_create_count": 0,
                    "skipped": True,
                    "skip_reason": f"No term found for academic year '{academic_year}'",
                    "errors": [],
                }
            return 0

        # Only query FeeStructures strictly matching the enrollment's academic_year
        active_subscriptions = list(
            ServiceSubscription.objects.filter(
                student=student, is_active=True
            ).values_list("service_id", flat=True)
        )

        fee_filter = Q(is_mandatory=True)
        if active_subscriptions:
            fee_filter |= Q(optional_service_id__in=active_subscriptions)

        fees = FeeStructure.objects.filter(
            academic_year=academic_year
        ).filter(fee_filter).prefetch_related("grade_levels", "classrooms")

        applicable_count = 0
        created_count = 0
        existing_count = 0
        would_create_count = 0
        errors = []

        for fee in fees:
            target_term = cls._resolve_target_term(fee, context_term=effective_term)
            if not target_term:
                # Fee is explicitly configured for another term (e.g. Second Term fee during First Term enrollment)
                continue

            if cls.is_student_applicable(
                student=student,
                fee_structure=fee,
                academic_year=academic_year,
                term=target_term,
            ):
                applicable_count += 1
                already_exists = cls.find_existing_obligation(
                    student=student,
                    fee_structure=fee,
                    term=target_term,
                ) is not None

                if already_exists:
                    existing_count += 1
                else:
                    # Invariant: PER_TERM + All Terms requires a matching FeeTermSchedule for target_term
                    if fee.recurrence == FeeRecurrence.PER_TERM and fee.term_id is None:
                        if not fee.term_schedules.filter(term=target_term).exists():
                            term_name = getattr(target_term, "name", str(target_term))
                            error_msg = (
                                f'No fee term schedule is configured for "{term_name}" '
                                f'on fee structure "{fee.name}" (ID {fee.pk}).'
                            )
                            if return_details:
                                errors.append(error_msg)
                                continue
                            else:
                                raise ValidationError(error_msg)

                    if dry_run:
                        would_create_count += 1
                    else:
                        created = cls.assign_fee_to_student(
                            fee_structure=fee,
                            student=student,
                            term=target_term,
                        )
                        if created:
                            created_count += 1
                        else:
                            existing_count += 1

        if return_details:
            return {
                "applicable_count": applicable_count,
                "created_count": created_count,
                "existing_count": existing_count,
                "would_create_count": would_create_count,
                "skipped": False,
                "skip_reason": None,
                "errors": errors,
            }

        return would_create_count if dry_run else created_count
