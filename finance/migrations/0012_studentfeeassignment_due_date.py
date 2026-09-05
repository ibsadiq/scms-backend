# Generated for SSync Fee Recurrence Architecture Phase 5B (Due-Date Snapshot Foundation)

from django.db import migrations, models


def backfill_fee_assignment_due_dates(apps, schema_editor):
    StudentFeeAssignment = apps.get_model("finance", "StudentFeeAssignment")

    assignments_to_update = []
    # Evaluate assignments that have a linked fee_structure and fee_structure.due_date
    for assignment in StudentFeeAssignment.objects.select_related("fee_structure", "term").all():
        fs = assignment.fee_structure
        if not fs or not fs.due_date:
            continue

        target_due_date = None
        # Rule 1: FeeStructure has a specific term matching the assignment term
        if fs.term_id is not None and fs.term_id == assignment.term_id:
            target_due_date = fs.due_date
        # Rule 2: Assignment term exists and FeeStructure.due_date falls within term date bounds
        elif (
            assignment.term
            and assignment.term.start_date
            and assignment.term.end_date
            and assignment.term.start_date <= fs.due_date <= assignment.term.end_date
        ):
            target_due_date = fs.due_date

        if target_due_date is not None:
            assignment.due_date = target_due_date
            assignments_to_update.append(assignment)

    if assignments_to_update:
        StudentFeeAssignment.objects.bulk_update(
            assignments_to_update,
            ["due_date"],
            batch_size=500,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0011_fee_recurrence_identity_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentfeeassignment",
            name="due_date",
            field=models.DateField(
                blank=True,
                db_index=True,
                help_text="Concrete historical due date for this financial obligation",
                null=True,
            ),
        ),
        migrations.RunPython(
            backfill_fee_assignment_due_dates,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
