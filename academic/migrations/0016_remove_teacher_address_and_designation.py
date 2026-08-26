from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("academic", "0015_staff_academic_qualification_staff_address_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="teacher",
            name="address",
        ),
        migrations.RemoveField(
            model_name="teacher",
            name="designation",
        ),
    ]
