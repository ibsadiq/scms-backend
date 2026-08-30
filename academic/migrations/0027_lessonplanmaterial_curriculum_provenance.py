from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("academic", "0026_decouple_curriculum_domain"),
    ]

    operations = [
        migrations.AddField(
            model_name="lessonplanmaterial",
            name="content",
            field=models.TextField(
                blank=True,
                help_text="Textual lesson material such as notes, examples, or instructions.",
            ),
        ),
        migrations.AddField(
            model_name="lessonplanmaterial",
            name="source_curriculum_resource",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="lesson_plan_material_copies",
                to="academic.curriculumresource",
            ),
        ),
        migrations.AddField(
            model_name="lessonplanmaterial",
            name="source_resource_title",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="lessonplanmaterial",
            name="source_resource_type",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="lessonplanmaterial",
            name="source_curriculum_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="lessonplanmaterial",
            name="source_curriculum_version",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddConstraint(
            model_name="lessonplanmaterial",
            constraint=models.UniqueConstraint(
                condition=models.Q(source_curriculum_resource__isnull=False),
                fields=("lesson_plan", "source_curriculum_resource"),
                name="unique_curriculum_resource_per_lesson_plan",
            ),
        ),
    ]
