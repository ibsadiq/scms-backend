# tenants/migrations/0005_inspector.py

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        # Last applied tenants migration
        ('tenants', '0004_delete_schoolsettings_remove_client_is_active_and_more'),
        # users migration we just wrote — Inspector needs CustomUser to exist first
        ('users', '0002_add_is_inspector'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Inspector',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False
                )),
                ('title', models.CharField(
                    blank=True, max_length=100
                )),
                ('organisation', models.CharField(
                    blank=True, max_length=150
                )),
                ('access_level', models.CharField(
                    choices=[
                        ('global',   'All Schools'),
                        ('assigned', 'Assigned Schools'),
                    ],
                    default='assigned',
                    max_length=20,
                )),
                ('is_active', models.BooleanField(default=True)),
                ('notes',     models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='inspector_profile',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('assigned_tenants', models.ManyToManyField(
                    blank=True,
                    related_name='inspectors',
                    to='tenants.client',
                )),
            ],
            options={
                'ordering': ['user__email'],
            },
        ),
    ]