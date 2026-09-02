from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("cbt", "0006_offlineexampackage")]

    operations = [
        migrations.AddField(
            model_name="examattempt",
            name="offline_package",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="attempt",
                to="cbt.offlineexampackage",
            ),
        ),
        migrations.AddField(
            model_name="examattempt",
            name="start_source",
            field=models.CharField(
                choices=[("ONLINE", "Online"), ("OFFLINE_RECONCILED", "Offline reconciled")],
                default="ONLINE",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="examattempt",
            name="client_reported_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="examattempt",
            name="server_reconciled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="examattempt",
            name="client_reported_submitted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="attemptanswerevent",
            name="origin",
            field=models.CharField(
                choices=[("ONLINE", "Online"), ("OFFLINE_SYNC", "Offline sync")],
                default="ONLINE",
                max_length=16,
            ),
        ),
    ]
