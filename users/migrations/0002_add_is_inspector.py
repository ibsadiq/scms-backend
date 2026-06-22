# users/migrations/0002_add_is_inspector.py

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='is_inspector',
            field=models.BooleanField(
                default=False,
                help_text='Public official with read-only access to assigned schools',
            ),
        ),
    ]