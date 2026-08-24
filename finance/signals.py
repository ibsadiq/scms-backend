from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from academic.models import Student
from administration.models import Term

from .models import FeeStructure


@receiver(post_save, sender=FeeStructure)
def schedule_mandatory_fee_assignment(sender, instance, created, **kwargs):
    if created and instance.is_mandatory:
        fee_id = instance.pk
        transaction.on_commit(lambda: _assign_fee(fee_id))


@receiver(pre_save, sender=Student)
def capture_previous_student_fee_status(sender, instance, **kwargs):
    previous = (
        Student.objects.filter(pk=instance.pk).values_list(
            "is_active", "graduation_date", "date_dismissed"
        ).first() if instance.pk else None
    )
    instance._previous_fee_active = bool(
        previous and previous[0] and not previous[1] and not previous[2]
    )


@receiver(post_save, sender=Student)
def schedule_fees_for_student(sender, instance, created, **kwargs):
    became_active = instance.status == "Active" and (
        created or not getattr(instance, "_previous_fee_active", False)
    )
    if not became_active:
        return
    current_term = Term.objects.filter(
        academic_year__active_year=True,
        start_date__lte=timezone.localdate(),
        end_date__gte=timezone.localdate(),
    ).first()
    if current_term:
        student_id, term_id = instance.pk, current_term.pk
        transaction.on_commit(lambda: _assign_student(student_id, term_id))


@receiver(post_save, sender=Term)
def schedule_fees_for_term(sender, instance, created, **kwargs):
    if not created:
        return
    fee_ids = list(
        FeeStructure.objects.filter(
            academic_year=instance.academic_year,
            is_mandatory=True,
        ).filter(term=instance).values_list("pk", flat=True)
    ) + list(
        FeeStructure.objects.filter(
            academic_year=instance.academic_year,
            is_mandatory=True,
            term__isnull=True,
        ).values_list("pk", flat=True)
    )
    term_id = instance.pk
    transaction.on_commit(lambda: _assign_fees(fee_ids, term_id))


def _assign_fee(fee_id, term_id=None):
    from finance.services import FeeAssignmentService

    fee = FeeStructure.objects.get(pk=fee_id)
    term = Term.objects.get(pk=term_id) if term_id else None
    FeeAssignmentService.assign_fee(fee_structure=fee, term=term)


def _assign_fees(fee_ids, term_id):
    for fee_id in fee_ids:
        _assign_fee(fee_id, term_id)


def _assign_student(student_id, term_id):
    from finance.services import FeeAssignmentService

    FeeAssignmentService.assign_current_fees_to_student(
        student=Student.objects.get(pk=student_id),
        term=Term.objects.get(pk=term_id),
    )
