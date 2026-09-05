from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from finance.models import (
    AuditAction,
    FeePaymentAllocation,
    FinanceAuditLog,
    PaymentStatus,
    PaymentThrough,
    Receipt,
    StudentFeeAssignment,
)


class PaymentAllocationService:
    @classmethod
    def _validate_and_normalize_allocations(cls, allocations):
        """
        Validates raw allocation items, checks positive amounts,
        rejects duplicate assignments, and returns normalized list of dicts.
        """
        if not allocations:
            raise ValidationError({"allocations": "At least one fee allocation is required."})

        normalized = []
        seen_ids = set()
        for idx, item in enumerate(allocations):
            if not isinstance(item, dict):
                raise ValidationError({"allocations": f"Invalid allocation at index {idx}: must be an object."})

            raw_id = item.get("fee_assignment") or item.get("fee_assignment_id")
            if not raw_id:
                raise ValidationError({"allocations": f"Allocation at index {idx} is missing fee_assignment."})

            try:
                assignment_id = int(raw_id)
            except (ValueError, TypeError):
                raise ValidationError({"allocations": f"Invalid fee_assignment ID '{raw_id}' at index {idx}."})

            if assignment_id in seen_ids:
                raise ValidationError({"allocations": f"Duplicate fee assignment ID {assignment_id} in payment."})
            seen_ids.add(assignment_id)

            raw_amount = item.get("amount")
            if raw_amount is None:
                raise ValidationError({"allocations": f"Allocation for assignment {assignment_id} is missing amount."})

            try:
                amount = Decimal(str(raw_amount))
            except Exception:
                raise ValidationError({"allocations": f"Invalid amount '{raw_amount}' for assignment {assignment_id}."})

            if amount <= 0:
                raise ValidationError({"allocations": f"Allocation amount for assignment {assignment_id} must be positive."})

            normalized.append({
                "fee_assignment_id": assignment_id,
                "amount": amount,
            })

        return normalized

    @classmethod
    @transaction.atomic
    def record_payment_with_allocations(cls, *, receipt_data, allocations, actor=None):
        """
        Atomically creates a Receipt, its FeePaymentAllocations, updates
        StudentFeeAssignment balances, and writes a FinanceAuditLog entry.
        """
        # 1. Validate and normalize allocations payload
        normalized = cls._validate_and_normalize_allocations(allocations)
        total_allocated = sum((item["amount"] for item in normalized), Decimal("0.00"))

        # 2. Lock target StudentFeeAssignment records in deterministic PK order
        ids = sorted([item["fee_assignment_id"] for item in normalized])
        assignments = {
            assignment.pk: assignment
            for assignment in StudentFeeAssignment.objects.select_for_update(of=("self",))
            .select_related("student", "fee_structure")
            .filter(pk__in=ids).order_by("pk")
        }

        if len(assignments) != len(ids):
            missing_ids = set(ids) - set(assignments.keys())
            raise ValidationError({"allocations": f"Fee assignment(s) {sorted(missing_ids)} do not exist."})

        # 3. Same-student validation
        student_ids = {a.student_id for a in assignments.values()}
        if len(student_ids) != 1:
            raise ValidationError({"allocations": "All fee allocations must belong to the same student."})

        target_student_id = next(iter(student_ids))
        target_student = assignments[ids[0]].student

        explicit_student = receipt_data.get("student") or receipt_data.get("student_id")
        if explicit_student:
            explicit_student_id = explicit_student.id if hasattr(explicit_student, "id") else int(explicit_student)
            if explicit_student_id != target_student_id:
                raise ValidationError({"student": "Specified student does not match the student on the fee assignments."})

        # 4. Validate balances & waived status
        for item in normalized:
            assignment = assignments[item["fee_assignment_id"]]
            if assignment.is_waived:
                raise ValidationError({
                    "allocations": f"Cannot allocate payment to waived fee '{assignment.fee_structure.name}'."
                })
            if item["amount"] > assignment.balance:
                raise ValidationError({
                    "allocations": f"Cannot allocate ₦{item['amount']:,.2f} - fee '{assignment.fee_structure.name}' balance is only ₦{assignment.balance:,.2f}."
                })

        # 5. Validate explicit receipt amount if provided
        explicit_amount = receipt_data.get("amount")
        if explicit_amount is not None:
            explicit_amount = Decimal(str(explicit_amount))
            if explicit_amount != total_allocated:
                raise ValidationError({
                    "amount": f"Receipt amount (₦{explicit_amount:,.2f}) does not match sum of allocations (₦{total_allocated:,.2f})."
                })

        # 6. Resolve Receipt.term semantics
        # If all assignments share the exact same concrete term, use it; otherwise None
        distinct_terms = {a.term_id for a in assignments.values()}
        if len(distinct_terms) == 1 and None not in distinct_terms:
            resolved_term_id = next(iter(distinct_terms))
        else:
            resolved_term_id = None

        # 7. Create Receipt
        payer_name = (receipt_data.get("payer") or target_student.full_name or "Unknown").strip()
        payment_date = receipt_data.get("payment_date") or timezone.now().date()
        paid_through = receipt_data.get("paid_through") or PaymentThrough.CASH
        reference_number = receipt_data.get("reference_number") or ""
        status_val = receipt_data.get("status") or PaymentStatus.COMPLETED
        remarks = receipt_data.get("remarks") or ""

        receipt = Receipt(
            student=target_student,
            payer=payer_name,
            amount=total_allocated,
            paid_through=paid_through,
            term_id=resolved_term_id,
            payment_date=payment_date,
            reference_number=reference_number,
            status=status_val,
            received_by=actor,
            remarks=remarks,
        )
        receipt.full_clean()
        receipt.save()  # Triggers PostgreSQL advisory lock for receipt_number

        # 8. Create FeePaymentAllocation records (save() updates assignment.amount_paid and last_payment_date)
        created_allocations = []
        for item in normalized:
            alloc = FeePaymentAllocation.objects.create(
                receipt=receipt,
                fee_assignment=assignments[item["fee_assignment_id"]],
                amount=item["amount"],
                allocated_by=actor,
            )
            created_allocations.append(alloc)

        # 9. Audit Logging
        FinanceAuditLog.objects.create(
            user=actor,
            action=AuditAction.PAYMENT_RECORDED,
            target_student=target_student,
            description=f"Recorded payment of ₦{receipt.amount:,.2f} from {target_student.full_name} ({target_student.admission_number or 'No Adm'}) across {len(created_allocations)} fee item(s).",
            metadata={
                "amount": float(receipt.amount),
                "receipt_id": receipt.id,
                "receipt_number": receipt.receipt_number,
                "allocations_count": len(created_allocations),
                "allocations": [
                    {"fee_assignment_id": a.fee_assignment_id, "amount": float(a.amount)}
                    for a in created_allocations
                ],
            },
        )

        return receipt

    @classmethod
    @transaction.atomic
    def allocate(cls, *, receipt, allocations, actor=None):
        """
        Allocates funds from an existing unallocated receipt to fee assignments.
        Preserved for backwards compatibility and existing endpoint allocate_to_fees.
        """
        receipt = Receipt.objects.select_for_update().get(pk=receipt.pk)
        normalized = cls._validate_and_normalize_allocations(allocations)
        total = sum((item["amount"] for item in normalized), Decimal("0.00"))

        if total <= 0 or total > receipt.unallocated_amount:
            raise ValidationError({
                "allocations": f"Total allocation (₦{total:,.2f}) exceeds available receipt balance (₦{receipt.unallocated_amount:,.2f})."
            })

        ids = sorted([item["fee_assignment_id"] for item in normalized])
        assignments = {
            assignment.pk: assignment
            for assignment in StudentFeeAssignment.objects.select_for_update()
            .select_related("student", "fee_structure")
            .filter(pk__in=ids).order_by("pk")
        }

        if len(assignments) != len(ids):
            missing = set(ids) - set(assignments.keys())
            raise ValidationError({"allocations": f"Fee assignment(s) {sorted(missing)} do not exist."})

        for item in normalized:
            assignment = assignments[item["fee_assignment_id"]]
            if receipt.student_id and receipt.student_id != assignment.student_id:
                raise ValidationError({"allocations": "Receipt and fee assignments must belong to the same student."})
            if assignment.is_waived:
                raise ValidationError({"allocations": f"Cannot allocate payment to waived fee '{assignment.fee_structure.name}'."})
            if item["amount"] > assignment.balance:
                raise ValidationError({
                    "allocations": f"Cannot allocate ₦{item['amount']:,.2f} - fee '{assignment.fee_structure.name}' balance is only ₦{assignment.balance:,.2f}."
                })

        return [
            FeePaymentAllocation.objects.create(
                receipt=receipt,
                fee_assignment=assignments[item["fee_assignment_id"]],
                amount=item["amount"],
                allocated_by=actor,
            )
            for item in normalized
        ]

    @classmethod
    @transaction.atomic
    def reverse_receipt(cls, *, receipt, actor=None):
        """
        Atomically reverses a Receipt:
        - Locks receipt and related fee assignments in deterministic order.
        - Decrements amount_paid on all affected StudentFeeAssignments via receipt.delete().
        - Records a single cohesive PAYMENT_REVERSED FinanceAuditLog entry with full allocation metadata.
        - Deletes the Receipt and cascades deletion of FeePaymentAllocations.
        """
        locked_receipt = Receipt.objects.select_for_update().get(pk=receipt.pk)
        student_name = (
            locked_receipt.student.full_name
            if locked_receipt.student
            else (locked_receipt.payer or "Unknown Payer")
        )
        adm_no = (
            locked_receipt.student.admission_number
            if (locked_receipt.student and locked_receipt.student.admission_number)
            else "No Adm"
        )
        allocations_snapshot = [
            {"fee_assignment_id": a.fee_assignment_id, "amount": float(a.amount)}
            for a in locked_receipt.fee_allocations.all()
        ]

        FinanceAuditLog.objects.create(
            user=actor,
            action=AuditAction.PAYMENT_REVERSED,
            target_student=locked_receipt.student,
            description=f"Reversed payment of ₦{locked_receipt.amount:,.2f} from {student_name} ({adm_no}) across {len(allocations_snapshot)} fee item(s).",
            metadata={
                "amount": float(locked_receipt.amount),
                "receipt_id": locked_receipt.id,
                "receipt_number": locked_receipt.receipt_number,
                "allocations_count": len(allocations_snapshot),
                "allocations": allocations_snapshot,
            },
        )

        locked_receipt.delete()
        return True
