from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0006_alter_inspector_assigned_tenants_alter_inspector_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='onboarding_completed',
            field=models.BooleanField(
                default=False,
                help_text='True once the school admin has completed (or skipped) the first-run setup wizard',
            ),
        ),
    ]
