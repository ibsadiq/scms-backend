from collections import defaultdict
from decimal import Decimal
from django.db import connection

from finance.models import FeeStructure, StudentFeeAssignment


class FeeIdentityAuditService:
    """
    Read-only service to audit fee structure logical keys, collisions,
    and StudentFeeAssignment snapshot integrity for a tenant.
    """

    @classmethod
    def audit(cls, schema_name=None):
        active_schema = schema_name or getattr(connection, "schema_name", "public")

        # 1. Audit FeeStructures
        fee_structures = list(
            FeeStructure.objects.select_related("academic_year", "term").all().order_by("id")
        )
        total_fs = len(fee_structures)
        blank_fs = [fs for fs in fee_structures if not fs.logical_fee_key]
        blank_fs_count = len(blank_fs)

        key_to_fs = defaultdict(list)
        for fs in fee_structures:
            if fs.logical_fee_key:
                key_to_fs[fs.logical_fee_key].append(fs)

        distinct_keys_count = len(key_to_fs)

        duplicate_key_reports = []
        cross_year_keys_count = 0
        same_year_duplicate_keys_count = 0
        semantic_collision_keys_count = 0

        for key, fs_list in key_to_fs.items():
            if len(fs_list) > 1:
                # Group by academic year
                year_map = defaultdict(list)
                fee_types = set()
                names = set()

                for fs in fs_list:
                    year_name = fs.academic_year.name if fs.academic_year else "No Year"
                    year_map[year_name].append(fs)
                    fee_types.add(fs.fee_type)
                    names.add(fs.name.strip().lower())

                is_cross_year = len(year_map) > 1
                is_same_year_dup = any(len(v) > 1 for v in year_map.values())
                is_semantic_collision = len(fee_types) > 1 or len(names) > 1

                if is_cross_year:
                    cross_year_keys_count += 1
                if is_same_year_dup:
                    same_year_duplicate_keys_count += 1
                if is_semantic_collision:
                    semantic_collision_keys_count += 1

                duplicate_key_reports.append(
                    {
                        "logical_fee_key": key,
                        "total_structures": len(fs_list),
                        "is_cross_year": is_cross_year,
                        "is_same_year_duplicate": is_same_year_dup,
                        "is_semantic_collision": is_semantic_collision,
                        "structures": [
                            {
                                "id": fs.id,
                                "name": fs.name,
                                "academic_year": fs.academic_year.name if fs.academic_year else None,
                                "term": fs.term.name if fs.term else "All Terms",
                                "recurrence": fs.recurrence,
                                "applicability": fs.applicability,
                                "fee_type": fs.fee_type,
                                "amount": fs.amount,
                            }
                            for fs in fs_list
                        ],
                    }
                )

        # 2. Audit StudentFeeAssignments
        assignments = list(
            StudentFeeAssignment.objects.select_related(
                "fee_structure", "academic_year", "fee_structure__academic_year"
            ).all().order_by("id")
        )
        total_assignments = len(assignments)

        blank_key_assignments = 0
        null_year_assignments = 0
        key_mismatches = 0
        recurrence_mismatches = 0
        sample_discrepancies = []

        for a in assignments:
            has_discrepancy = False
            fs = a.fee_structure

            if not a.logical_fee_key:
                blank_key_assignments += 1
                has_discrepancy = True

            if not a.academic_year_id:
                null_year_assignments += 1
                has_discrepancy = True

            if fs:
                if a.logical_fee_key and fs.logical_fee_key and a.logical_fee_key != fs.logical_fee_key:
                    key_mismatches += 1
                    has_discrepancy = True
                if a.recurrence and fs.recurrence and a.recurrence != fs.recurrence:
                    recurrence_mismatches += 1
                    has_discrepancy = True

            if has_discrepancy and len(sample_discrepancies) < 20:
                sample_discrepancies.append(
                    {
                        "assignment_id": a.id,
                        "student_id": a.student_id,
                        "fee_structure_id": a.fee_structure_id,
                        "assignment_key": a.logical_fee_key,
                        "structure_key": fs.logical_fee_key if fs else None,
                        "assignment_recurrence": a.recurrence,
                        "structure_recurrence": fs.recurrence if fs else None,
                        "assignment_year": a.academic_year.name if a.academic_year else None,
                        "structure_year": fs.academic_year.name if fs and fs.academic_year else None,
                    }
                )

        from django.db.models import Count
        onetime_conflicts = (
            StudentFeeAssignment.objects
            .filter(recurrence="ONE_TIME")
            .exclude(logical_fee_key="")
            .values("student_id", "logical_fee_key")
            .annotate(dup_count=Count("id"))
            .filter(dup_count__gt=1)
        )
        onetime_conflict_count = onetime_conflicts.count()

        annual_conflicts = (
            StudentFeeAssignment.objects
            .filter(recurrence="ANNUAL")
            .exclude(logical_fee_key="")
            .filter(academic_year__isnull=False)
            .values("student_id", "logical_fee_key", "academic_year_id")
            .annotate(dup_count=Count("id"))
            .filter(dup_count__gt=1)
        )
        annual_conflict_count = annual_conflicts.count()

        return {
            "schema_name": active_schema,
            "fee_structures": {
                "total": total_fs,
                "blank_keys": blank_fs_count,
                "distinct_keys": distinct_keys_count,
                "cross_year_keys_count": cross_year_keys_count,
                "same_year_duplicate_keys_count": same_year_duplicate_keys_count,
                "semantic_collision_keys_count": semantic_collision_keys_count,
                "duplicate_keys": duplicate_key_reports,
            },
            "student_fee_assignments": {
                "total": total_assignments,
                "blank_logical_key_count": blank_key_assignments,
                "null_academic_year_count": null_year_assignments,
                "key_mismatches_count": key_mismatches,
                "recurrence_mismatches_count": recurrence_mismatches,
                "onetime_conflict_groups_count": onetime_conflict_count,
                "annual_conflict_groups_count": annual_conflict_count,
                "sample_discrepancies": sample_discrepancies,
            },
        }
