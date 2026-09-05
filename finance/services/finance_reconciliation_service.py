from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Coalesce

from finance.models import (
    FeePaymentAllocation,
    FeeRecurrence,
    Receipt,
    StudentFeeAssignment,
)


class FinanceReconciliationService:
    """
    Read-only accounting and reconciliation service for multi-fee receipts,
    allocations, assignments, and reporting breakdowns.
    """

    @classmethod
    def get_assignment_allocation_total(cls, assignment_id: int) -> Decimal:
        """Sum of all posted FeePaymentAllocation amounts for a specific fee assignment."""
        result = FeePaymentAllocation.objects.filter(
            fee_assignment_id=assignment_id
        ).aggregate(
            total=Coalesce(Sum('amount'), Decimal('0.00'))
        )
        return result['total']

    @classmethod
    def get_receipt_allocation_total(cls, receipt_id: int) -> Decimal:
        """Sum of all FeePaymentAllocation amounts for a specific receipt."""
        result = FeePaymentAllocation.objects.filter(
            receipt_id=receipt_id
        ).aggregate(
            total=Coalesce(Sum('amount'), Decimal('0.00'))
        )
        return result['total']

    @classmethod
    def get_receipt_unallocated_amount(cls, receipt_id: int) -> Decimal:
        """Unallocated balance for a specific receipt (receipt.amount - allocated_total)."""
        receipt = Receipt.objects.get(pk=receipt_id)
        allocated = cls.get_receipt_allocation_total(receipt_id)
        return max(Decimal('0.00'), receipt.amount - allocated)

    @classmethod
    def audit_receipt(cls, receipt: Receipt | int) -> Dict[str, Any]:
        """
        Audit a receipt's transaction amount against its linked allocation rows.
        """
        if isinstance(receipt, int):
            receipt = Receipt.objects.get(pk=receipt)

        allocations = list(receipt.fee_allocations.all())
        allocated_total = sum((a.amount for a in allocations), Decimal('0.00'))
        unallocated = receipt.amount - allocated_total

        return {
            "receipt_id": receipt.id,
            "receipt_number": receipt.receipt_number,
            "amount": receipt.amount,
            "allocated_amount": allocated_total,
            "unallocated_amount": unallocated,
            "allocation_count": len(allocations),
            "is_fully_allocated": (receipt.amount == allocated_total),
            "is_over_allocated": (allocated_total > receipt.amount),
            "allocations": [
                {
                    "id": a.id,
                    "fee_assignment_id": a.fee_assignment_id,
                    "amount": a.amount,
                }
                for a in allocations
            ],
        }

    @classmethod
    def audit_assignment(cls, assignment: StudentFeeAssignment | int) -> Dict[str, Any]:
        """
        Audit a StudentFeeAssignment's recorded amount_paid against sum of its allocations.
        """
        if isinstance(assignment, int):
            assignment = StudentFeeAssignment.objects.select_related(
                "fee_structure", "student"
            ).get(pk=assignment)

        allocation_total = cls.get_assignment_allocation_total(assignment.pk)
        drift = assignment.amount_paid - allocation_total

        return {
            "assignment_id": assignment.id,
            "student_id": assignment.student_id,
            "fee_name": assignment.fee_structure.name if assignment.fee_structure else "Unknown",
            "amount_owed": assignment.amount_owed,
            "amount_paid": assignment.amount_paid,
            "allocation_total": allocation_total,
            "balance": assignment.balance,
            "is_waived": assignment.is_waived,
            "is_in_sync": (drift == Decimal('0.00')),
            "drift": drift,
        }

    @classmethod
    def audit_student(cls, student_id: int) -> Dict[str, Any]:
        """
        Audits all fee obligations, receipts, and allocations for a student.
        """
        assignments = StudentFeeAssignment.objects.filter(student_id=student_id)
        receipts = Receipt.objects.filter(student_id=student_id)

        # Assignment totals
        active_assignments = assignments.filter(is_waived=False)
        total_owed = active_assignments.aggregate(
            t=Coalesce(Sum('amount_owed'), Decimal('0.00'))
        )['t']
        total_paid = assignments.aggregate(
            t=Coalesce(Sum('amount_paid'), Decimal('0.00'))
        )['t']
        total_balance = sum((a.balance for a in active_assignments), Decimal('0.00'))

        # Allocation total
        allocations_total = FeePaymentAllocation.objects.filter(
            fee_assignment__student_id=student_id
        ).aggregate(t=Coalesce(Sum('amount'), Decimal('0.00')))['t']

        # Receipt transaction total (each receipt counted once)
        receipts_total = receipts.aggregate(
            t=Coalesce(Sum('amount'), Decimal('0.00'))
        )['t']

        unallocated_funds = max(Decimal('0.00'), receipts_total - allocations_total)

        return {
            "student_id": student_id,
            "total_owed": total_owed,
            "total_paid": total_paid,
            "total_balance": total_balance,
            "allocations_total": allocations_total,
            "receipts_total": receipts_total,
            "unallocated_funds": unallocated_funds,
            "is_in_sync": (total_paid == allocations_total),
            "assignment_count": assignments.count(),
            "receipt_count": receipts.count(),
        }

    @classmethod
    def get_payment_method_breakdown(
        cls,
        *,
        academic_year_id: Optional[int] = None,
        term_id: Optional[int] = None,
        fee_type: Optional[str] = None,
        classroom_id: Optional[int] = None,
        student_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Calculates payment method totals safely using FeePaymentAllocation.amount.
        Guarantees that multi-fee receipts do not inflate or multiply method totals.
        """
        allocations = FeePaymentAllocation.objects.all()

        if student_id:
            allocations = allocations.filter(fee_assignment__student_id=student_id)
        if classroom_id:
            allocations = allocations.filter(fee_assignment__student__classroom_id=classroom_id)
        if term_id:
            allocations = allocations.filter(fee_assignment__term_id=term_id)
        elif academic_year_id:
            allocations = allocations.filter(
                Q(fee_assignment__term__academic_year_id=academic_year_id)
                | Q(fee_assignment__academic_year_id=academic_year_id)
            )
        if fee_type:
            allocations = allocations.filter(fee_assignment__fee_structure__fee_type=fee_type)

        breakdown = (
            allocations.values(method=F('receipt__paid_through'))
            .annotate(
                total=Coalesce(Sum('amount'), Decimal('0.00')),
                allocation_count=Count('id'),
            )
            .order_by('-total')
        )

        return [
            {
                "method": row["method"] or "Unknown",
                "total": row["total"],
                "allocation_count": row["allocation_count"],
            }
            for row in breakdown
        ]

    @classmethod
    def get_fee_type_breakdown(
        cls,
        *,
        academic_year_id: Optional[int] = None,
        term_id: Optional[int] = None,
        classroom_id: Optional[int] = None,
        student_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Groups fee collections by FeeStructure.fee_type using FeePaymentAllocation.amount.
        """
        allocations = FeePaymentAllocation.objects.all()

        if student_id:
            allocations = allocations.filter(fee_assignment__student_id=student_id)
        if classroom_id:
            allocations = allocations.filter(fee_assignment__student__classroom_id=classroom_id)
        if term_id:
            allocations = allocations.filter(fee_assignment__term_id=term_id)
        elif academic_year_id:
            allocations = allocations.filter(
                Q(fee_assignment__term__academic_year_id=academic_year_id)
                | Q(fee_assignment__academic_year_id=academic_year_id)
            )

        breakdown = (
            allocations.values(fee_type=F('fee_assignment__fee_structure__fee_type'))
            .annotate(
                total=Coalesce(Sum('amount'), Decimal('0.00')),
                allocation_count=Count('id'),
            )
            .order_by('-total')
        )

        return [
            {
                "fee_type": row["fee_type"] or "Other",
                "total": row["total"],
                "allocation_count": row["allocation_count"],
            }
            for row in breakdown
        ]

    @classmethod
    def get_academic_year_breakdown(
        cls,
        *,
        student_id: Optional[int] = None,
        classroom_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Groups collections by the academic year associated with the fee obligation,
        NOT from receipt header terms.
        """
        allocations = FeePaymentAllocation.objects.select_related(
            "fee_assignment__term__academic_year",
            "fee_assignment__academic_year",
        )
        if student_id:
            allocations = allocations.filter(fee_assignment__student_id=student_id)
        if classroom_id:
            allocations = allocations.filter(fee_assignment__student__classroom_id=classroom_id)

        year_map: Dict[str, Dict[str, Any]] = {}
        for alloc in allocations:
            year_obj = (
                alloc.fee_assignment.academic_year
                or (alloc.fee_assignment.term.academic_year if alloc.fee_assignment.term else None)
            )
            year_name = year_obj.name if year_obj else "Unassigned / Legacy"
            year_id = year_obj.id if year_obj else None

            if year_name not in year_map:
                year_map[year_name] = {
                    "academic_year_id": year_id,
                    "academic_year_name": year_name,
                    "total": Decimal('0.00'),
                    "allocation_count": 0,
                }
            year_map[year_name]["total"] += alloc.amount
            year_map[year_name]["allocation_count"] += 1

        results = list(year_map.values())
        results.sort(key=lambda x: x["total"], reverse=True)
        return results

    @classmethod
    def get_term_breakdown(
        cls,
        *,
        academic_year_id: Optional[int] = None,
        student_id: Optional[int] = None,
        classroom_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Groups collections by the term associated with the fee obligation.
        Obligations without a term (Annual, One-Time) are grouped under 'Non-Term / Annual'.
        """
        allocations = FeePaymentAllocation.objects.select_related(
            "fee_assignment__term",
            "fee_assignment__fee_structure",
        )
        if student_id:
            allocations = allocations.filter(fee_assignment__student_id=student_id)
        if classroom_id:
            allocations = allocations.filter(fee_assignment__student__classroom_id=classroom_id)
        if academic_year_id:
            allocations = allocations.filter(
                Q(fee_assignment__term__academic_year_id=academic_year_id)
                | Q(fee_assignment__academic_year_id=academic_year_id)
            )

        term_map: Dict[str, Dict[str, Any]] = {}
        for alloc in allocations:
            fa = alloc.fee_assignment
            is_annual_or_onetime = (
                getattr(fa, 'recurrence', None) in (FeeRecurrence.ANNUAL, FeeRecurrence.ONE_TIME)
                or getattr(getattr(fa, 'fee_structure', None), 'recurrence', None) in (FeeRecurrence.ANNUAL, FeeRecurrence.ONE_TIME)
                or fa.term is None
            )
            if is_annual_or_onetime:
                term_name = "Annual / One-Time"
                term_id_val = None
            else:
                term_obj = fa.term
                term_name = term_obj.name if term_obj else "Annual / One-Time"
                term_id_val = term_obj.id if term_obj else None

            if term_name not in term_map:
                term_map[term_name] = {
                    "term_id": term_id_val,
                    "term_name": term_name,
                    "total": Decimal('0.00'),
                    "allocation_count": 0,
                }
            term_map[term_name]["total"] += alloc.amount
            term_map[term_name]["allocation_count"] += 1

        results = list(term_map.values())
        results.sort(key=lambda x: x["total"], reverse=True)
        return results

    @classmethod
    def reconcile_school_totals(
        cls,
        *,
        academic_year_id: Optional[int] = None,
        term_id: Optional[int] = None,
        classroom_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        School-wide reconciliation comparing:
        - Transaction-level received (Receipt.amount)
        - Allocation-level applied (FeePaymentAllocation.amount)
        - Student fee assignment obligations (amount_owed, amount_paid, balance)
        """
        # 1. Assignment aggregates
        assignments = StudentFeeAssignment.objects.all()
        if classroom_id:
            assignments = assignments.filter(student__classroom_id=classroom_id)
        if term_id:
            assignments = assignments.filter(term_id=term_id)
        elif academic_year_id:
            assignments = assignments.filter(
                Q(term__academic_year_id=academic_year_id)
                | Q(academic_year_id=academic_year_id)
            )

        active_assignments = assignments.filter(is_waived=False)
        total_owed = active_assignments.aggregate(
            t=Coalesce(Sum('amount_owed'), Decimal('0.00'))
        )['t']
        total_paid = assignments.aggregate(
            t=Coalesce(Sum('amount_paid'), Decimal('0.00'))
        )['t']
        total_balance = sum((a.balance for a in active_assignments), Decimal('0.00'))

        # 2. Allocation aggregates
        allocations = FeePaymentAllocation.objects.all()
        if classroom_id:
            allocations = allocations.filter(fee_assignment__student__classroom_id=classroom_id)
        if term_id:
            allocations = allocations.filter(fee_assignment__term_id=term_id)
        elif academic_year_id:
            allocations = allocations.filter(
                Q(fee_assignment__term__academic_year_id=academic_year_id)
                | Q(fee_assignment__academic_year_id=academic_year_id)
            )

        total_allocated = allocations.aggregate(
            t=Coalesce(Sum('amount'), Decimal('0.00'))
        )['t']

        # 3. Receipt aggregates (Scoped distinct receipts)
        if term_id or academic_year_id or classroom_id:
            # Receipts linked to matching allocations
            receipt_ids = allocations.values_list('receipt_id', flat=True).distinct()
            receipts_qs = Receipt.objects.filter(id__in=receipt_ids)
        else:
            receipts_qs = Receipt.objects.all()

        total_received = receipts_qs.aggregate(
            t=Coalesce(Sum('amount'), Decimal('0.00'))
        )['t']
        receipt_count = receipts_qs.count()
        allocation_count = allocations.count()

        unallocated = max(Decimal('0.00'), total_received - total_allocated)

        return {
            "total_received": total_received,
            "total_allocated": total_allocated,
            "total_unallocated": unallocated,
            "assignments_total_owed": total_owed,
            "assignments_total_paid": total_paid,
            "assignments_total_balance": total_balance,
            "receipt_count": receipt_count,
            "allocation_count": allocation_count,
            "is_allocation_assignment_in_sync": (total_allocated == total_paid),
        }
