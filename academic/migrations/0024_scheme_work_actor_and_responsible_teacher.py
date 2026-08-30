from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_created_by_user(apps, schema_editor):
    SchemeOfWork = apps.get_model("academic", "SchemeOfWork")
    for scheme in SchemeOfWork.objects.select_related("responsible_teacher__user").iterator():
        teacher = scheme.responsible_teacher
        if teacher and teacher.user_id:
            scheme.created_by_id = teacher.user_id
            scheme.save(update_fields=["created_by"])


class Migration(migrations.Migration):
    dependencies = [
        ("academic", "0023_scheme_of_work_published_adoption"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameField(
            model_name="schemeofwork",
            old_name="created_by",
            new_name="responsible_teacher",
        ),
        migrations.AlterField(
            model_name="schemeofwork",
            name="responsible_teacher",
            field=models.ForeignKey(
                blank=True,
                db_index=False,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="responsible_schemes_of_work",
                to="academic.teacher",
            ),
        ),
        migrations.AddField(
            model_name="schemeofwork",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_schemes_of_work",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name="schemeofwork",
            index=models.Index(fields=["responsible_teacher"], name="acad_sow_resp_teacher_idx"),
        ),
        migrations.RunPython(backfill_created_by_user, migrations.RunPython.noop),
    ]
