# Generated for SSync Fee Recurrence Architecture Phase 2A (Deterministic Identity Backfill)

from django.db import migrations
from django.utils.text import slugify


def backfill_fee_identity(apps, schema_editor):
    FeeStructure = apps.get_model("finance", "FeeStructure")
    StudentFeeAssignment = apps.get_model("finance", "StudentFeeAssignment")

    # 1. Backfill FeeStructure.logical_fee_key
    # Only backfill where logical_fee_key is empty/null, preserving explicit keys.
    fs_to_update = []
    for fs in FeeStructure.objects.all():
        if not fs.logical_fee_key:
            generated_slug = slugify(fs.name) if fs.name else ""
            fs.logical_fee_key = generated_slug if generated_slug else f"fee-{fs.pk}"
            fs_to_update.append(fs)

    if fs_to_update:
        FeeStructure.objects.bulk_update(fs_to_update, ["logical_fee_key"], batch_size=500)

    # Build cache of FeeStructure metadata by ID: (logical_fee_key, academic_year_id)
    fs_cache = {}
    for fs in FeeStructure.objects.all():
        key = fs.logical_fee_key or (slugify(fs.name) if fs.name else f"fee-{fs.pk}")
        fs_cache[fs.pk] = (key, fs.academic_year_id)

    # 2. Backfill StudentFeeAssignment identity snapshots (logical_fee_key and academic_year only)
    # Crucially: Do NOT modify StudentFeeAssignment.recurrence at all.
    # Historical assignments retain their existing recurrence (including Phase 1 PER_TERM default).
    assignments_to_update = []
    for assignment in StudentFeeAssignment.objects.select_related("term").all():
        changed = False
        fs_info = fs_cache.get(assignment.fee_structure_id)

        if fs_info:
            fs_key, fs_year_id = fs_info

            # Backfill logical_fee_key if missing
            if not assignment.logical_fee_key:
                assignment.logical_fee_key = fs_key
                changed = True

            # Backfill academic_year if None
            if not assignment.academic_year_id:
                target_year_id = fs_year_id or (
                    assignment.term.academic_year_id if assignment.term_id else None
                )
                if target_year_id:
                    assignment.academic_year_id = target_year_id
                    changed = True

        if changed:
            assignments_to_update.append(assignment)

    if assignments_to_update:
        StudentFeeAssignment.objects.bulk_update(
            assignments_to_update,
            ["logical_fee_key", "academic_year"],
            batch_size=500,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0009_fee_recurrence_phase1"),
    ]

    operations = [
        migrations.RunPython(
            backfill_fee_identity,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
