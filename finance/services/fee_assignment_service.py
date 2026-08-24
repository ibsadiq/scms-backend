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
        class_levels = list(fee_structure.class_levels.all())
        if grade_levels:
            students = students.filter(classroom__class_level__grade_level__in=grade_levels)
        if class_levels:
            students = students.filter(classroom__class_level__in=class_levels)

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
