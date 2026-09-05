from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django_tenants.utils import schema_context

from finance.services.fee_identity_audit_service import FeeIdentityAuditService
from tenants.models import Client


class Command(BaseCommand):
    help = (
        "Read-only audit of fee structure logical keys, collisions, "
        "and StudentFeeAssignment snapshot integrity for a tenant schema."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            type=str,
            default=None,
            help="Tenant schema name to execute against (e.g. 'green_valley_academy').",
        )
        parser.add_argument(
            "--show-all-duplicates",
            action="store_true",
            default=False,
            help="Display full breakdown of all duplicate logical fee keys.",
        )

    def handle(self, *args, **options):
        schema_name = options.get("schema")
        current_connection_schema = getattr(connection, "schema_name", None)

        if schema_name:
            if not Client.objects.filter(schema_name=schema_name).exists():
                raise CommandError(f"Tenant schema '{schema_name}' does not exist.")
            with schema_context(schema_name):
                self._execute_audit(options, schema_name)
        elif current_connection_schema and current_connection_schema != "public":
            self._execute_audit(options, current_connection_schema)
        else:
            raise CommandError(
                "A tenant schema must be specified via --schema=<schema_name> "
                "or by running in a tenant schema context."
            )

    def _execute_audit(self, options, active_schema):
        audit_data = FeeIdentityAuditService.audit(schema_name=active_schema)
        fs_data = audit_data["fee_structures"]
        sfa_data = audit_data["student_fee_assignments"]

        self.stdout.write("=" * 70)
        self.stdout.write("FEE IDENTITY & RECURRENCE SNAPSHOT AUDIT REPORT")
        self.stdout.write("=" * 70)
        self.stdout.write(f"Tenant Schema:                         {active_schema}")
        self.stdout.write("-" * 70)

        # 1. FeeStructures
        self.stdout.write("FEESTRUCTURE SUMMARY:")
        self.stdout.write(f"  Total FeeStructures:                 {fs_data['total']}")
        self.stdout.write(f"  Blank logical keys:                  {fs_data['blank_keys']}")
        self.stdout.write(f"  Distinct logical fee keys:           {fs_data['distinct_keys']}")
        self.stdout.write(f"  Keys spanning multiple years:        {fs_data['cross_year_keys_count']} (Expected cross-year identity)")
        self.stdout.write(f"  Keys with same-year duplicates:      {fs_data['same_year_duplicate_keys_count']} (Potential same-year collision)")
        self.stdout.write(f"  Keys with semantic collisions:       {fs_data['semantic_collision_keys_count']} (Differing fee types/names)")
        self.stdout.write("-" * 70)

        # 2. StudentFeeAssignments
        self.stdout.write("STUDENTFEEASSIGNMENT SNAPSHOT SUMMARY:")
        self.stdout.write(f"  Total StudentFeeAssignments:         {sfa_data['total']}")
        self.stdout.write(f"  Assignments with blank logical key:  {sfa_data['blank_logical_key_count']}")
        self.stdout.write(f"  Assignments with null academic year: {sfa_data['null_academic_year_count']}")
        self.stdout.write(f"  Assignments key != FeeStructure key: {sfa_data['key_mismatches_count']} (Historical policy drift)")
        self.stdout.write(f"  Assignments rec != FeeStructure rec: {sfa_data['recurrence_mismatches_count']} (Historical policy drift)")
        self.stdout.write(f"  ONE_TIME conflict groups:            {sfa_data.get('onetime_conflict_groups_count', 0)}")
        self.stdout.write(f"  ANNUAL conflict groups:              {sfa_data.get('annual_conflict_groups_count', 0)}")
        self.stdout.write("=" * 70)

        # 3. Duplicate Key Details
        dup_keys = fs_data["duplicate_keys"]
        if dup_keys:
            self.stdout.write("\nLOGICAL KEY COLLISION DETAILS:")
            for item in dup_keys:
                key = item["logical_fee_key"]
                tags = []
                if item["is_cross_year"]:
                    tags.append("CROSS-YEAR")
                if item["is_same_year_duplicate"]:
                    tags.append("SAME-YEAR-DUPLICATE")
                if item["is_semantic_collision"]:
                    tags.append("SEMANTIC-COLLISION")

                category_tag = ", ".join(tags) if tags else "DUPLICATE"
                self.stdout.write(f"\n* Key: '{key}' [{category_tag}] ({item['total_structures']} records)")
                for fs in item["structures"]:
                    term_display = fs["term"] or "All Terms"
                    year_display = fs["academic_year"] or "No Year"
                    self.stdout.write(
                        f"  - ID {fs['id']:<4} | {fs['name']:<25} | {year_display:<10} | "
                        f"{term_display:<12} | Recurrence: {fs['recurrence']:<10} | "
                        f"Applicability: {fs['applicability']:<15} | Type: {fs['fee_type']}"
                    )
        else:
            self.stdout.write("\nNo duplicate logical keys found across FeeStructures.")

        # 4. Discrepancy Samples
        samples = sfa_data["sample_discrepancies"]
        if samples:
            self.stdout.write("\n" + "-" * 70)
            self.stdout.write("STUDENTFEEASSIGNMENT DISCREPANCY SAMPLES (First 20):")
            for s in samples:
                self.stdout.write(
                    f"  - Assignment ID {s['assignment_id']}: Student {s['student_id']}, FS {s['fee_structure_id']} | "
                    f"Key: '{s['assignment_key']}' (FS: '{s['structure_key']}'), "
                    f"Recurrence: '{s['assignment_recurrence']}' (FS: '{s['structure_recurrence']}'), "
                    f"Year: '{s['assignment_year']}' (FS: '{s['structure_year']}')"
                )

        self.stdout.write("\nAudit complete (read-only; no database records were modified).\n")
