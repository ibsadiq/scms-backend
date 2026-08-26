from django.db import migrations, models
import django.db.models.deletion


def migrate_classrooms_forward(apps, schema_editor):
    ClassRoom = apps.get_model("academic", "ClassRoom")
    ClassLevel = apps.get_model("academic", "ClassLevel")
    for cr in ClassRoom.objects.all():
        if cr.name_id:
            try:
                cl = ClassLevel.objects.get(pk=cr.name_id)
                cr.grade_level_id = cl.grade_level_id
                cr.classroom_name = cl.name
                cr.save(update_fields=["grade_level", "classroom_name"])
            except ClassLevel.DoesNotExist:
                pass


def migrate_classrooms_backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("academic", "0017_alter_gradelevel_system_code"),
        ("finance", "0007_feestructure_remove_class_levels_add_classrooms"),
    ]

    operations = [
        migrations.AddField(
            model_name="classroom",
            name="grade_level",
            field=models.ForeignKey(
                help_text="Academic stage (e.g. JSS 1 / Year 7)",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="classrooms",
                to="academic.gradelevel",
            ),
        ),
        migrations.AddField(
            model_name="classroom",
            name="classroom_name",
            field=models.CharField(
                default="",
                help_text="Classroom name (e.g. 'Oleander', 'A', 'Gold')",
                max_length=150,
            ),
        ),
        migrations.RunPython(
            code=migrate_classrooms_forward,
            reverse_code=migrate_classrooms_backward,
        ),
        migrations.RemoveConstraint(
            model_name="classroom",
            name="unique_classroom_per_stream",
        ),
        migrations.RemoveField(
            model_name="classroom",
            name="name",
        ),
        migrations.RenameField(
            model_name="classroom",
            old_name="classroom_name",
            new_name="name",
        ),
        migrations.AlterField(
            model_name="classroom",
            name="grade_level",
            field=models.ForeignKey(
                help_text="Academic stage (e.g. JSS 1 / Year 7)",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="classrooms",
                to="academic.gradelevel",
            ),
        ),
        migrations.AlterField(
            model_name="classroom",
            name="stream",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional academic pathway (e.g. Science, Commercial, Arts)",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="classrooms",
                to="academic.stream",
            ),
        ),
        migrations.AlterField(
            model_name="classroom",
            name="class_teacher",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="homeroom_classrooms",
                to="academic.teacher",
            ),
        ),
        migrations.AlterModelOptions(
            name="classroom",
            options={"ordering": ("grade_level__sequence_order", "name")},
        ),
        migrations.AlterModelOptions(
            name="stream",
            options={"ordering": ("name",)},
        ),
        migrations.AddConstraint(
            model_name="classroom",
            constraint=models.UniqueConstraint(
                condition=models.Q(("stream__isnull", False)),
                fields=("grade_level", "stream", "name"),
                name="unique_classroom_with_stream",
            ),
        ),
        migrations.AddConstraint(
            model_name="classroom",
            constraint=models.UniqueConstraint(
                condition=models.Q(("stream__isnull", True)),
                fields=("grade_level", "name"),
                name="unique_classroom_without_stream",
            ),
        ),
        migrations.RemoveField(
            model_name="student",
            name="class_level",
        ),
        migrations.AlterField(
            model_name="assessmenttemplate",
            name="applicable_classes",
            field=models.ManyToManyField(
                blank=True,
                help_text="Which grade levels can use this template",
                to="academic.gradelevel",
            ),
        ),
        migrations.DeleteModel(
            name="ClassLevel",
        ),
    ]
