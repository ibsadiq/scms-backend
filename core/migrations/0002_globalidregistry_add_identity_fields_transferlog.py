# Generated migration — extends GlobalIDRegistry with identity/location fields
# and adds TransferLog for cross-school transfer audit trail.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        # ── GlobalIDRegistry new fields ───────────────────────────────────────
        migrations.AddField(
            model_name='globalidregistry',
            name='first_name',
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name='globalidregistry',
            name='last_name',
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name='globalidregistry',
            name='date_of_birth',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='globalidregistry',
            name='national_id',
            field=models.CharField(blank=True, max_length=100, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='globalidregistry',
            name='current_schema',
            field=models.CharField(blank=True, db_index=True, max_length=63),
        ),
        migrations.AddField(
            model_name='globalidregistry',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),

        # ── Extra index on (entity_type, current_schema) ──────────────────────
        migrations.AddIndex(
            model_name='globalidregistry',
            index=models.Index(
                fields=['entity_type', 'current_schema'],
                name='core_global_entity_schema_idx',
            ),
        ),

        # ── TransferLog ───────────────────────────────────────────────────────
        migrations.CreateModel(
            name='TransferLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('entity_id',      models.CharField(db_index=True, max_length=50)),
                ('entity_type',    models.CharField(max_length=20)),
                ('from_schema',    models.CharField(blank=True, max_length=63)),
                ('to_schema',      models.CharField(max_length=63)),
                ('person_name',    models.CharField(blank=True, max_length=300)),
                ('notes',          models.TextField(blank=True)),
                ('transferred_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-transferred_at'],
                'app_label': 'core',
                'indexes': [
                    models.Index(fields=['entity_id', 'transferred_at'],
                                 name='core_transfer_entity_idx'),
                ],
            },
        ),
    ]
