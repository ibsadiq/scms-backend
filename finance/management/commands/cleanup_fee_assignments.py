from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django_tenants.utils import schema_context

from finance.models import FeeStructure, StudentFeeAssignment
from finance.services.fee_assignment_service import FeeAssignmentService
from tenants.models import Client


class Command(BaseCommand):
    help = (
        "Safely identify and clean up incorrectly assigned StudentFeeAssignment records "
        "that violate a FeeStructure's current applicability rules."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            type=str,
            default=None,
            help="Tenant schema name to execute against (e.g. 'green_valley_academy').",
        )
        parser.add_argument(
            "--fee-structure-id",
            type=int,
            required=True,
            help="Primary key (ID) of the FeeStructure to clean up.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Preview cleanup candidates and safety checks without modifying or deleting any database records.",
        )

    def handle(self, *args, **options):
        schema_name = options.get("schema")
        current_connection_schema = getattr(connection, "schema_name", None)

        if schema_name:
            if not Client.objects.filter(schema_name=schema_name).exists():
                raise CommandError(f"Tenant schema '{schema_name}' does not exist.")
            with schema_context(schema_name):
                self._execute_cleanup(options, schema_name)
        elif current_connection_schema and current_connection_schema != "public":
            self._execute_cleanup(options, current_connection_schema)
        else:
            raise CommandError(
                "A tenant schema must be specified via --schema=<schema_name> "
                "or by running within a tenant schema context."
            )

    def _execute_cleanup(self, options, active_schema):
        fee_structure_id = options.get("fee_structure_id")
        dry_run = options.get("dry_run", False)

        fee_structure = (
            FeeStructure.objects.select_related("academic_year", "term")
            .filter(pk=fee_structure_id)
            .first()
        )
        if not fee_structure:
            raise CommandError(
                f"FeeStructure with ID {fee_structure_id} does not exist in schema '{active_schema}'."
            )

        mode_str = "DRY RUN" if dry_run else "LIVE EXECUTION"

        # 1. Fetch all assignments for this FeeStructure
        assignments = (
            StudentFeeAssignment.objects.filter(fee_structure=fee_structure)
            .select_related("student", "term", "academic_year")
            .prefetch_related("payment_allocations", "adjustments")
            .order_by("pk")
        )

        total_assignments = assignments.count()
        applicable_count = 0
        inapplicable_count = 0

        safe_to_delete = []
        blocked_by_payment = []
        blocked_by_allocation = []
        blocked_by_waiver = []
        other_blocked = []

        candidate_rows = []

        for a in assignments:
            is_applicable = FeeAssignmentService.is_student_applicable(
                student=a.student,
                fee_structure=fee_structure,
                academic_year=fee_structure.academic_year,
                term=a.term,
            )

            student_name = a.student.full_name if a.student else "Unknown Student"
            student_adm = (a.student.admission_number if a.student else "") or "N/A"

            if is_applicable:
                applicable_count += 1
            else:
                inapplicable_count += 1

                # Safety checks
                has_paid = a.amount_paid > Decimal("0.00")
                has_alloc = a.payment_allocations.exists()
                is_waived = a.is_waived or a.waived_date is not None or a.waived_by_id is not None
                has_adjustments = a.adjustments.exists()

                if has_paid:
                    blocked_by_payment.append(a)
                    status_desc = "BLOCKED (Payment)"
                elif has_alloc:
                    blocked_by_allocation.append(a)
                    status_desc = "BLOCKED (Allocation)"
                elif is_waived:
                    blocked_by_waiver.append(a)
                    status_desc = "BLOCKED (Waived)"
                elif has_adjustments:
                    other_blocked.append(a)
                    status_desc = "BLOCKED (Adjustment)"
                else:
                    safe_to_delete.append(a)
                    status_desc = "SAFE TO DELETE"

                candidate_rows.append(
                    {
                        "id": a.pk,
                        "student": student_name,
                        "adm_no": student_adm,
                        "amount_owed": a.amount_owed,
                        "amount_paid": a.amount_paid,
                        "status": status_desc,
                    }
                )

        total_blocked = (
            len(blocked_by_payment)
            + len(blocked_by_allocation)
            + len(blocked_by_waiver)
            + len(other_blocked)
        )

        # 2. Print Summary Report
        self.stdout.write("=" * 60)
        self.stdout.write("Fee Assignment Cleanup Summary")
        self.stdout.write("=" * 60)
        self.stdout.write(f"Tenant Schema:          {active_schema}")
        self.stdout.write(f"Fee Structure ID:       {fee_structure.pk}")
        self.stdout.write(f"Fee Name:               {fee_structure.name}")
        self.stdout.write(f"Logical Fee Key:        {fee_structure.logical_fee_key or '(None)'}")
        self.stdout.write(f"Academic Year:          {fee_structure.academic_year.name if fee_structure.academic_year else '(None)'}")
        self.stdout.write(f"Recurrence:             {fee_structure.recurrence}")
        self.stdout.write(f"Applicability:          {fee_structure.applicability}")
        self.stdout.write(f"Mode:                   {mode_str}")
        self.stdout.write("-" * 60)
        self.stdout.write(f"Total assignments:      {total_assignments}")
        self.stdout.write(f"Still applicable:       {applicable_count}")
        self.stdout.write(f"Inapplicable:           {inapplicable_count}")
        self.stdout.write(f"Safe to delete:         {len(safe_to_delete)}")
        self.stdout.write(f"Blocked by payment:     {len(blocked_by_payment)}")
        self.stdout.write(f"Blocked by allocation:  {len(blocked_by_allocation)}")
        self.stdout.write(f"Blocked by waiver:      {len(blocked_by_waiver)}")
        self.stdout.write(f"Other blocked:          {len(other_blocked)}")
        self.stdout.write("=" * 60)

        # 3. Print Candidate Samples
        if candidate_rows:
            self.stdout.write("\nInapplicable Assignment Candidates:")
            self.stdout.write(
                f"{'Assignment ID':<15} | {'Student':<25} | {'Adm No':<18} | {'Owed':<10} | {'Paid':<10} | {'Status'}"
            )
            self.stdout.write("-" * 95)
            for row in candidate_rows[:20]:
                self.stdout.write(
                    f"{row['id']:<15} | {row['student'][:25]:<25} | {row['adm_no'][:18]:<18} | "
                    f"{row['amount_owed']:<10.2f} | {row['amount_paid']:<10.2f} | {row['status']}"
                )
            if len(candidate_rows) > 20:
                self.stdout.write(f"... and {len(candidate_rows) - 20} more candidate(s).")
            self.stdout.write("")

        # 4. Perform Live Deletion or Conclude Dry Run
        if dry_run:
            self.stdout.write(self.style.SUCCESS("No database changes were made (dry run).\n"))
            return

        if not safe_to_delete:
            self.stdout.write(
                self.style.WARNING("No safe inapplicable assignments found to delete.\n")
            )
            self.stdout.write(
                f"Deleted: 0\nBlocked: {total_blocked}\nPreserved applicable: {applicable_count}\n"
            )
            return

        # Live Deletion with atomic transaction and immediate re-verification
        with transaction.atomic():
            safe_ids = [a.pk for a in safe_to_delete]

            # Re-fetch and lock the records to be deleted
            locked_assignments = list(
                StudentFeeAssignment.objects.select_for_update().filter(pk__in=safe_ids)
            )

            final_ids_to_delete = []
            final_blocked = 0

            for a in locked_assignments:
                # Re-verify applicability and financial safety
                is_still_applicable = FeeAssignmentService.is_student_applicable(
                    student=a.student,
                    fee_structure=fee_structure,
                    academic_year=fee_structure.academic_year,
                    term=a.term,
                )
                has_paid = a.amount_paid > Decimal("0.00")
                has_alloc = a.payment_allocations.exists()
                is_waived = a.is_waived or a.waived_date is not None or a.waived_by_id is not None
                has_adjustments = a.adjustments.exists()

                if (
                    not is_still_applicable
                    and not has_paid
                    and not has_alloc
                    and not is_waived
                    and not has_adjustments
                ):
                    final_ids_to_delete.append(a.pk)
                else:
                    final_blocked += 1

            deleted_count, _ = StudentFeeAssignment.objects.filter(
                pk__in=final_ids_to_delete
            ).delete()

        self.stdout.write(
            f"Deleted: {deleted_count}\n"
            f"Blocked: {total_blocked + final_blocked}\n"
            f"Preserved applicable: {applicable_count}\n"
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully cleaned up {deleted_count} invalid fee assignment(s).\n"
            )
        )
