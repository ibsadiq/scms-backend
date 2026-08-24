from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from finance.models import FeePaymentAllocation, Receipt, StudentFeeAssignment


class PaymentAllocationService:
    @classmethod
    @transaction.atomic
    def allocate(cls, *, receipt, allocations, actor=None):
        receipt = Receipt.objects.select_for_update().get(pk=receipt.pk)
        normalized = [
            {
                "fee_assignment_id": int(item["fee_assignment_id"]),
                "amount": Decimal(str(item["amount"])),
            }
            for item in allocations
        ]
        total = sum((item["amount"] for item in normalized), Decimal("0.00"))
        if total <= 0 or total > receipt.unallocated_amount:
            raise ValidationError({"allocations": "Total allocation exceeds the available receipt amount."})

        ids = sorted({item["fee_assignment_id"] for item in normalized})
        assignments = {
            assignment.pk: assignment
            for assignment in StudentFeeAssignment.objects.select_for_update()
            .filter(pk__in=ids).order_by("pk")
        }
        if len(assignments) != len(ids):
            raise ValidationError({"allocations": "One or more fee assignments do not exist."})

        totals = {}
        for item in normalized:
            assignment = assignments[item["fee_assignment_id"]]
            if receipt.student_id and receipt.student_id != assignment.student_id:
                raise ValidationError({"allocations": "Receipt and fee assignments must belong to the same student."})
            totals[assignment.pk] = totals.get(assignment.pk, Decimal("0.00")) + item["amount"]
        for assignment_id, amount in totals.items():
            if amount <= 0 or amount > assignments[assignment_id].balance:
                raise ValidationError({"allocations": f"Invalid amount for fee assignment {assignment_id}."})

        return [
            FeePaymentAllocation.objects.create(
                receipt=receipt,
                fee_assignment=assignments[item["fee_assignment_id"]],
                amount=item["amount"],
                allocated_by=actor,
            )
            for item in normalized
        ]
