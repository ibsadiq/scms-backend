from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def populate_topic_grade_level(apps, schema_editor):
    Topic = apps.get_model("academic", "Topic")

    topics = Topic.objects.exclude(class_level__isnull=True)

    for topic in topics.iterator():
        class_level = topic.class_level

        if class_level and class_level.grade_level_id:
            topic.grade_level_id = class_level.grade_level_id
            topic.save(update_fields=["grade_level"])


class Migration(migrations.Migration):

    dependencies = [
        ("academic", "0006_schoolsection"),
    ]

    operations = [
        # 1. Add new field as nullable first
        migrations.AddField(
            model_name="topic",
            name="grade_level",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="topics",
                to="academic.gradelevel",
            ),
        ),

        # 2. Backfill from old class_level relationship
        migrations.RunPython(
            populate_topic_grade_level,
            migrations.RunPython.noop,
        ),

        # 3. Other harmless additions
        migrations.AddField(
            model_name="topic",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="topic",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="topic",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),

        migrations.AddField(
            model_name="subtopic",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="subtopic",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="subtopic",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),

        # 4. Make grade_level required after data has been copied
        migrations.AlterField(
            model_name="topic",
            name="grade_level",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="topics",
                to="academic.gradelevel",
            ),
        ),

        # 5. Remove old relationship LAST
        migrations.RemoveField(
            model_name="topic",
            name="class_level",
        ),

        migrations.AlterModelOptions(
            name="topic",
            options={
                "ordering": [
                    "grade_level__sequence_order",
                    "subject__name",
                    "name",
                ]
            },
        ),
        migrations.AlterModelOptions(
            name="subtopic",
            options={"ordering": ["topic__name", "name"]},
        ),

        migrations.AddIndex(
            model_name="topic",
            index=models.Index(
                fields=["grade_level", "subject"],
                name="academic_to_grade_l_ee7d99_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="subtopic",
            index=models.Index(
                fields=["topic"],
                name="academic_su_topic_i_a1e8c2_idx",
            ),
        ),

        migrations.AddConstraint(
            model_name="topic",
            constraint=models.UniqueConstraint(
                fields=("grade_level", "subject", "name"),
                name="unique_topic_per_grade_subject",
            ),
        ),
        migrations.AddConstraint(
            model_name="subtopic",
            constraint=models.UniqueConstraint(
                fields=("topic", "name"),
                name="unique_subtopic_per_topic",
            ),
        ),
    ]