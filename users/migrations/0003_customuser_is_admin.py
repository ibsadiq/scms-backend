from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_add_is_inspector'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='is_admin',
            field=models.BooleanField(default=False, help_text='School-level administrator'),
        ),
    ]
