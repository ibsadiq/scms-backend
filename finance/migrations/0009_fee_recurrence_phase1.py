# Generated for SSync Fee Recurrence Architecture Phase 1 (Schema Only)

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("administration", "0002_initial"),
        ("finance", "0008_alter_feestructure_fee_type_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="feestructure",
            name="applicability",
            field=models.CharField(
                choices=[
                    ("ALL_ELIGIBLE", "All Eligible Students"),
                    ("NEW_STUDENTS_ONLY", "New Students Only"),
                ],
                default="ALL_ELIGIBLE",
                help_text="Eligibility: All Eligible Students or New Students Only",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="feestructure",
            name="logical_fee_key",
            field=models.SlugField(
                blank=True,
                default="",
                help_text="Stable identifier representing the same logical fee across academic years",
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name="feestructure",
            name="recurrence",
            field=models.CharField(
                choices=[
                    ("PER_TERM", "Every Term"),
                    ("ANNUAL", "Once Per Academic Year"),
                    ("ONE_TIME", "Once Per Student Lifetime"),
                ],
                default="PER_TERM",
                help_text="Billing frequency: Every Term, Once Per Academic Year, or Once Per Student Lifetime",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="studentfeeassignment",
            name="academic_year",
            field=models.ForeignKey(
                blank=True,
                help_text="Academic year in which this assignment obligation was incurred",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="fee_assignments",
                to="administration.academicyear",
            ),
        ),
        migrations.AddField(
            model_name="studentfeeassignment",
            name="logical_fee_key",
            field=models.SlugField(
                blank=True,
                default="",
                help_text="Historical snapshot of fee structure's logical identity",
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name="studentfeeassignment",
            name="recurrence",
            field=models.CharField(
                choices=[
                    ("PER_TERM", "Every Term"),
                    ("ANNUAL", "Once Per Academic Year"),
                    ("ONE_TIME", "Once Per Student Lifetime"),
                ],
                default="PER_TERM",
                help_text="Historical snapshot of fee structure's recurrence policy",
                max_length=20,
            ),
        ),
        migrations.AddIndex(
            model_name="studentfeeassignment",
            index=models.Index(
                fields=["logical_fee_key"],
                name="finance_stu_logical_944087_idx",
            ),
        ),
    ]
