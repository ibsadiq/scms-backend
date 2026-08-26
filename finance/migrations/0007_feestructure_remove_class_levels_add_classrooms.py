from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academic", "0017_alter_gradelevel_system_code"),
        ("finance", "0006_finance_integrity_constraints"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="feestructure",
            name="class_levels",
        ),
        migrations.AddField(
            model_name="feestructure",
            name="classrooms",
            field=models.ManyToManyField(
                blank=True,
                help_text="Leave blank to apply to all classrooms in the selected grade levels",
                related_name="fee_structures",
                to="academic.classroom",
            ),
        ),
    ]
