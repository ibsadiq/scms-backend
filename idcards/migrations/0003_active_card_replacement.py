import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("idcards", "0002_rfidcredential"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="idcard",
            name="status",
            field=models.CharField(
                choices=[
                    ("ACTIVE", "Active"), ("INACTIVE", "Inactive"),
                    ("REVOKED", "Revoked"), ("REPLACED", "Replaced"),
                ],
                db_index=True, default="ACTIVE", max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="idcard", name="replaces",
            field=models.OneToOneField(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="replacement_card", to="idcards.idcard",
            ),
        ),
        migrations.AddField(
            model_name="idcard", name="replacement_reason",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="idcard", name="replaced_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="idcard", name="replaced_by",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="replacement_id_cards", to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="idcard",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "ACTIVE")), fields=("student",),
                name="one_active_idcard_per_student",
            ),
        ),
        migrations.AddConstraint(
            model_name="idcard",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "ACTIVE")), fields=("staff",),
                name="one_active_idcard_per_staff",
            ),
        ),
    ]
