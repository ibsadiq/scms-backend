import uuid

import django.db.models.deletion
import decimal
import idcards.models
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


def forwards(apps, schema_editor):
    Template = apps.get_model("idcards", "IDCardTemplate")
    Version = apps.get_model("idcards", "IDCardTemplateVersion")
    Card = apps.get_model("idcards", "IDCard")

    for template in Template.objects.all().iterator():
        Template.objects.filter(pk=template.pk).update(
            public_id=uuid.uuid4(), is_archived=not template.is_active,
        )
        orientation = "LANDSCAPE" if template.width_mm >= template.height_mm else "PORTRAIT"
        status = "PUBLISHED" if template.is_active else "ARCHIVED"
        version = Version.objects.create(
            template_id=template.pk,
            version_number=1,
            status=status,
            width_mm=template.width_mm,
            height_mm=template.height_mm,
            orientation=orientation,
            # Preserve schema-v1 JSON exactly; no conversion occurs in ID1.
            front_layout=template.front_layout,
            back_layout=template.back_layout,
            published_at=template.updated_at if template.is_active else None,
        )
        updates = {"current_draft_version_id": None}
        if template.is_active:
            updates["current_published_version_id"] = version.pk
        Template.objects.filter(pk=template.pk).update(**updates)
        Card.objects.filter(template_id=template.pk).update(template_version_id=version.pk)


def backwards(apps, schema_editor):
    # The compatibility fields retained on IDCardTemplate already contain the
    # original dimensions and layouts, so deleting versions loses no v1 data.
    Template = apps.get_model("idcards", "IDCardTemplate")
    Template.objects.update(current_draft_version_id=None, current_published_version_id=None)


class Migration(migrations.Migration):
    dependencies = [
        ("idcards", "0003_active_card_replacement"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="idcardtemplate", name="public_id",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.AddField(
            model_name="idcardtemplate", name="description",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="idcardtemplate", name="is_archived",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="idcardtemplate", name="created_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="created_idcard_templates", to=settings.AUTH_USER_MODEL),
        ),
        migrations.CreateModel(
            name="IDCardTemplateVersion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("version_number", models.PositiveIntegerField()),
                ("status", models.CharField(choices=[("DRAFT", "Draft"), ("PUBLISHED", "Published"), ("ARCHIVED", "Archived")], db_index=True, default="DRAFT", max_length=10)),
                ("width_mm", models.DecimalField(decimal_places=2, default=decimal.Decimal("85.60"), max_digits=6)),
                ("height_mm", models.DecimalField(decimal_places=2, default=decimal.Decimal("53.98"), max_digits=6)),
                ("orientation", models.CharField(choices=[("LANDSCAPE", "Landscape"), ("PORTRAIT", "Portrait")], default="LANDSCAPE", max_length=10)),
                ("front_layout", models.JSONField(default=idcards.models.empty_layout_v2)),
                ("back_layout", models.JSONField(default=idcards.models.empty_layout_v2)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_idcard_template_versions", to=settings.AUTH_USER_MODEL)),
                ("published_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="published_idcard_template_versions", to=settings.AUTH_USER_MODEL)),
                ("created_from_version", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="derived_versions", to="idcards.idcardtemplateversion")),
                ("template", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="versions", to="idcards.idcardtemplate")),
            ],
            options={
                "ordering": ("template_id", "-version_number"),
                "constraints": [
                    models.UniqueConstraint(fields=("template", "version_number"), name="unique_idcard_template_version"),
                    models.UniqueConstraint(condition=Q(status="DRAFT"), fields=("template",), name="one_draft_idcard_template_version"),
                    models.CheckConstraint(condition=Q(width_mm__gt=0), name="idcard_version_width_positive"),
                    models.CheckConstraint(condition=Q(height_mm__gt=0), name="idcard_version_height_positive"),
                ],
            },
        ),
        migrations.AddField(
            model_name="idcardtemplate", name="current_draft_version",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="draft_for_templates", to="idcards.idcardtemplateversion"),
        ),
        migrations.AddField(
            model_name="idcardtemplate", name="current_published_version",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="published_for_templates", to="idcards.idcardtemplateversion"),
        ),
        migrations.AddField(
            model_name="idcard", name="template_version",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name="issued_cards", to="idcards.idcardtemplateversion"),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.AlterField(
            model_name="idcardtemplate", name="public_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="idcard", name="template_version",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                    related_name="issued_cards", to="idcards.idcardtemplateversion"),
        ),
    ]
