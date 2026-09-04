from decimal import Decimal

from django.db import IntegrityError, transaction

from academic.models import Student
from administration.models import Term
from finance.models import FeeStructure, ServiceSubscription, StudentFeeAssignment


class FeeAssignmentService:
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

        terms = [fee_structure.term] if fee_structure.term_id else [term] if term else list(
            Term.objects.filter(academic_year=fee_structure.academic_year).order_by("start_date")[:1]
        )
        created_count = 0
        for student in students.iterator(chunk_size=500):
            for assignment_term in terms:
                if not assignment_term or not fee_structure.applies_to_student(student, assignment_term):
                    continue
                try:
                    with transaction.atomic():
                        _, created = StudentFeeAssignment.objects.get_or_create(
                            student=student,
                            fee_structure=fee_structure,
                            term=assignment_term,
                            defaults={
                                "amount_owed": fee_structure.amount,
                                "amount_paid": Decimal("0.00"),
                            },
                        )
                except IntegrityError:
                    # The unique student/fee/term row won a concurrent race.
                    StudentFeeAssignment.objects.get(
                        student=student, fee_structure=fee_structure, term=assignment_term
                    )
                    created = False
                created_count += int(created)
        return created_count

    @classmethod
    def assign_current_fees_to_student(cls, *, student, term):
        assigned = 0
        fees = FeeStructure.objects.filter(
            is_mandatory=True, academic_year=term.academic_year
        )
        for fee in fees:
            if fee.applies_to_student(student, term):
                assigned += cls.assign_fee_to_student(
                    fee_structure=fee, student=student, term=term
                )
        return assigned

    @classmethod
    def assign_fee_to_student(cls, *, fee_structure, student, term):
        try:
            with transaction.atomic():
                _, created = StudentFeeAssignment.objects.get_or_create(
                    student=student,
                    fee_structure=fee_structure,
                    term=term,
                    defaults={
                        "amount_owed": fee_structure.amount,
                        "amount_paid": Decimal("0.00"),
                    },
                )
        except IntegrityError:
            StudentFeeAssignment.objects.get(
                student=student, fee_structure=fee_structure, term=term
            )
            created = False
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
    def sync_fees_for_enrollment(cls, *, enrollment, term=None):
        """
        Authoritative fee synchronization for an active student enrollment.
        Uses enrollment.student, enrollment.classroom, and enrollment.academic_year.
        Works before, during, and after term commencement dates.
        Strictly confines fee assignments to enrollment.academic_year.
        """
        if not enrollment or not enrollment.is_active:
            return 0

        student = enrollment.student
        classroom = enrollment.classroom
        academic_year = enrollment.academic_year

        if not student or not student.is_active or not classroom or not academic_year:
            return 0

        # Ensure student snapshot has classroom set in-memory for applies_to_student checks
        if student.classroom_id != classroom.pk:
            student.classroom = classroom

        effective_term = term or cls.resolve_effective_term(academic_year)
        if not effective_term:
            return 0

        # Only query FeeStructures strictly matching the enrollment's academic_year
        from django.db.models import Q
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

        assigned_count = 0
        for fee in fees:
            target_term = fee.term if fee.term_id else effective_term

            if fee.term_id and fee.term_id != effective_term.pk:
                # Fee is explicitly configured for another term (e.g. Second Term fee during First Term enrollment)
                continue

            if fee.applies_to_student(student, target_term):
                assigned_count += cls.assign_fee_to_student(
                    fee_structure=fee,
                    student=student,
                    term=target_term,
                )

        return assigned_count

