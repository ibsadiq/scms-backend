import uuid

from django.db import migrations, models


def populate_document_public_ids(apps, schema_editor):
    AdmissionDocument = apps.get_model("academic", "AdmissionDocument")
    for document in AdmissionDocument.objects.filter(public_id__isnull=True).iterator():
        document.public_id = uuid.uuid4()
        document.save(update_fields=["public_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("academic", "0011_admissionnumbersequence"),
    ]

    operations = [
        migrations.AddField(
            model_name="admissiondocument",
            name="public_id",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(
            populate_document_public_ids,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="admissiondocument",
            name="public_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
