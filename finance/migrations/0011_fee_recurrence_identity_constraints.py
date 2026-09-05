# Generated for SSync Fee Recurrence Architecture Phase 2B (Identity Constraints & Preflight)

from django.core.exceptions import ValidationError
from django.db import connection, migrations, models
from django.db.models import Count, Q


def preflight_check_recurrence_constraints(apps, schema_editor):
    StudentFeeAssignment = apps.get_model("finance", "StudentFeeAssignment")
    active_schema = getattr(connection, "schema_name", "unknown")

    # 1. Detect ONE_TIME duplicate collisions
    onetime_duplicates = (
        StudentFeeAssignment.objects
        .filter(recurrence="ONE_TIME")
        .exclude(logical_fee_key="")
        .values("student_id", "logical_fee_key")
        .annotate(dup_count=Count("id"))
        .filter(dup_count__gt=1)
    )

    if onetime_duplicates.exists():
        details = []
        for dup in onetime_duplicates[:5]:
            sample_ids = list(
                StudentFeeAssignment.objects.filter(
                    student_id=dup["student_id"],
                    logical_fee_key=dup["logical_fee_key"],
                    recurrence="ONE_TIME",
                ).values_list("id", flat=True)[:5]
            )
            details.append(
                f"Student ID {dup['student_id']}, key '{dup['logical_fee_key']}': "
                f"{dup['dup_count']} assignments (Sample IDs: {sample_ids})"
            )
        sample_str = "; ".join(details)
        raise ValidationError(
            f"Preflight validation failed in tenant schema '{active_schema}': "
            f"Found {onetime_duplicates.count()} ONE_TIME collision group(s) on (student, logical_fee_key). "
            f"Collisions: {sample_str}. "
            "Resolve these duplicate financial obligations before applying ONE_TIME unique constraints."
        )

    # 2. Detect ANNUAL duplicate collisions
    annual_duplicates = (
        StudentFeeAssignment.objects
        .filter(recurrence="ANNUAL")
        .exclude(logical_fee_key="")
        .filter(academic_year__isnull=False)
        .values("student_id", "logical_fee_key", "academic_year_id")
        .annotate(dup_count=Count("id"))
        .filter(dup_count__gt=1)
    )

    if annual_duplicates.exists():
        details = []
        for dup in annual_duplicates[:5]:
            sample_ids = list(
                StudentFeeAssignment.objects.filter(
                    student_id=dup["student_id"],
                    logical_fee_key=dup["logical_fee_key"],
                    academic_year_id=dup["academic_year_id"],
                    recurrence="ANNUAL",
                ).values_list("id", flat=True)[:5]
            )
            details.append(
                f"Student ID {dup['student_id']}, key '{dup['logical_fee_key']}', Year ID {dup['academic_year_id']}: "
                f"{dup['dup_count']} assignments (Sample IDs: {sample_ids})"
            )
        sample_str = "; ".join(details)
        raise ValidationError(
            f"Preflight validation failed in tenant schema '{active_schema}': "
            f"Found {annual_duplicates.count()} ANNUAL collision group(s) on (student, logical_fee_key, academic_year). "
            f"Collisions: {sample_str}. "
            "Resolve these duplicate financial obligations before applying ANNUAL unique constraints."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0010_fee_identity_backfill"),
    ]

    operations = [
        # 1. Preflight validation before introducing constraints
        migrations.RunPython(
            preflight_check_recurrence_constraints,
            reverse_code=migrations.RunPython.noop,
        ),
        # 2. Remove redundant single-column index on logical_fee_key (field already has db_index=True)
        migrations.RemoveIndex(
            model_name="studentfeeassignment",
            name="finance_stu_logical_944087_idx",
        ),
        # 3. Add conditional unique constraint for ONE_TIME fees
        migrations.AddConstraint(
            model_name="studentfeeassignment",
            constraint=models.UniqueConstraint(
                condition=Q(recurrence="ONE_TIME") & ~Q(logical_fee_key=""),
                fields=["student", "logical_fee_key"],
                name="finance_assignment_uniq_onetime_student_key",
            ),
        ),
        # 4. Add conditional unique constraint for ANNUAL fees
        migrations.AddConstraint(
            model_name="studentfeeassignment",
            constraint=models.UniqueConstraint(
                condition=Q(recurrence="ANNUAL") & ~Q(logical_fee_key="") & Q(academic_year__isnull=False),
                fields=["student", "logical_fee_key", "academic_year"],
                name="finance_assignment_uniq_annual_student_key_year",
            ),
        ),
    ]
