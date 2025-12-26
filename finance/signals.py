# signals.py
from django.db import models
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from decimal import Decimal
from academic.models import Student
from administration.models import Term
from .models import FeeStructure, StudentFeeAssignment


@receiver(post_save, sender=FeeStructure)
def auto_assign_mandatory_fees(sender, instance, created, **kwargs):
    """
    When a mandatory fee structure is created, automatically assign it
    to all applicable students.
    """
    if created and instance.is_mandatory:
        assigned_count = instance.auto_assign_to_students()
        print(f"Auto-assigned {assigned_count} students to {instance.name}")


@receiver(post_save, sender=Student)
def assign_fees_to_new_student(sender, instance, created, **kwargs):
    """
    When a new student is created or their grade/class changes,
    assign all applicable mandatory fees.
    """
    if instance.status != 'Active':
        return

    # Get current/active term
    try:
        current_term = Term.objects.filter(
            academic_year__active_year=True,
            start_date__lte=timezone.now().date(),
            end_date__gte=timezone.now().date()
        ).first()
    except:
        current_term = None

    if not current_term:
        return

    # Find all mandatory fees that apply to this student
    mandatory_fees = FeeStructure.objects.filter(
        is_mandatory=True,
        academic_year=current_term.academic_year
    )

    assigned_count = 0
    for fee_structure in mandatory_fees:
        if fee_structure.applies_to_student(instance, current_term):
            _, fee_created = StudentFeeAssignment.objects.get_or_create(
                student=instance,
                fee_structure=fee_structure,
                term=current_term,
                defaults={
                    'amount_owed': fee_structure.amount,
                    'amount_paid': Decimal('0.00'),
                }
            )
            if fee_created:
                assigned_count += 1

    if assigned_count > 0:
        print(f"Assigned {assigned_count} fees to {instance.full_name}")


@receiver(post_save, sender=Term)
def assign_fees_for_new_term(sender, instance, created, **kwargs):
    """
    When a new term is created, assign all mandatory fees for that term
    to applicable students.
    """
    if not created:
        return

    # Find all mandatory fees for this academic year that apply to this term
    mandatory_fees = FeeStructure.objects.filter(
        is_mandatory=True,
        academic_year=instance.academic_year
    ).filter(
        models.Q(term=instance) | models.Q(term__isnull=True)
    )

    total_assigned = 0
    for fee_structure in mandatory_fees:
        assigned = fee_structure.auto_assign_to_students(term=instance)
        total_assigned += assigned

    if total_assigned > 0:
        print(f"Assigned {total_assigned} fee assignments for new term: {instance.name}")


# Add this to your app's apps.py:
"""
from django.apps import AppConfig

class FinancialConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'financial'

    def ready(self):
        import financial.signals  # noqa
"""
