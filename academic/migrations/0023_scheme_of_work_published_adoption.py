import django.db.models.deletion
from django.db import migrations, models


def normalize_scheme_item_order(apps, schema_editor):
    SchemeOfWorkItem = apps.get_model("academic", "SchemeOfWorkItem")
    scheme_ids = SchemeOfWorkItem.objects.values_list("scheme_id", flat=True).distinct()
    for scheme_id in scheme_ids.iterator():
        item_ids = list(
            SchemeOfWorkItem.objects.filter(scheme_id=scheme_id)
            .order_by("week_start", "order", "id")
            .values_list("id", flat=True)
        )
        for position, item_id in enumerate(item_ids, start=1):
            SchemeOfWorkItem.objects.filter(id=item_id).update(order=position)


class Migration(migrations.Migration):
    dependencies = [("academic", "0022_numbersequence_and_more")]

    operations = [
        migrations.RenameField(
            model_name="schemeofworkitem", old_name="week_number", new_name="week_start"
        ),
        migrations.RemoveIndex(
            model_name="schemeofworkitem", name="academic_sc_scheme__380b60_idx"
        ),
        migrations.RemoveConstraint(
            model_name="schemeofworkitem", name="unique_scheme_item_order_per_week"
        ),
        migrations.AddField(
            model_name="schemeofworkitem", name="week_end",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="schemeofworkitem", name="entry_type",
            field=models.CharField(
                choices=[("INSTRUCTION", "Instruction"), ("REVISION", "Revision"),
                         ("ASSESSMENT", "Assessment"), ("EXAMINATION", "Examination"),
                         ("BREAK", "Break"), ("PREPARATION", "Preparation"),
                         ("CLOSING", "Closing"), ("OTHER", "Other")],
                default="INSTRUCTION", max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="schemeofworkitem", name="published_scheme_entry",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="adopted_scheme_items", to="academic.publishedschemeentry",
            ),
        ),
        migrations.AddField(model_name="schemeofworkitem", name="content_summary", field=models.TextField(blank=True)),
        migrations.AddField(model_name="schemeofworkitem", name="teacher_activities", field=models.TextField(blank=True)),
        migrations.AddField(model_name="schemeofworkitem", name="learner_activities", field=models.TextField(blank=True)),
        migrations.AddField(model_name="schemeofworkitem", name="learning_resources", field=models.TextField(blank=True)),
        migrations.AlterField(
            model_name="schemeofworkitem", name="week_start",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="schemeofworkitem", name="curriculum_topic",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="scheme_items", to="academic.curriculumtopic",
            ),
        ),
        migrations.AlterModelOptions(
            name="schemeofworkitem", options={"ordering": ["order", "week_start", "id"]}
        ),
        migrations.RunPython(normalize_scheme_item_order, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name="schemeofworkitem",
            index=models.Index(fields=["scheme", "week_start", "order"], name="scheme_item_week_order_idx"),
        ),
        migrations.AddConstraint(
            model_name="schemeofworkitem",
            constraint=models.UniqueConstraint(fields=("scheme", "order"), name="unique_scheme_item_order"),
        ),
        migrations.AddConstraint(
            model_name="schemeofworkitem",
            constraint=models.UniqueConstraint(
                condition=models.Q(("published_scheme_entry__isnull", False)),
                fields=("scheme", "published_scheme_entry"), name="unique_adopted_entry_per_scheme",
            ),
        ),
        migrations.AddConstraint(
            model_name="schemeofworkitem",
            constraint=models.CheckConstraint(
                condition=models.Q(week_start__isnull=True) | models.Q(week_start__gt=0),
                name="scheme_item_week_start_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="schemeofworkitem",
            constraint=models.CheckConstraint(
                condition=models.Q(week_end__isnull=True) | models.Q(week_end__gt=0),
                name="scheme_item_week_end_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="schemeofworkitem",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(week_end__isnull=True)
                    | (
                        models.Q(week_start__isnull=False)
                        & models.Q(week_end__gte=models.F("week_start"))
                    )
                ),
                name="scheme_item_week_range_valid",
            ),
        ),
    ]
