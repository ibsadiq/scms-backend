from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("academic", "0010_staff_identity_foundation"),
    ]

    operations = [
        migrations.CreateModel(
            name="AdmissionNumberSequence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("year", models.PositiveIntegerField(unique=True)),
                ("last_value", models.PositiveBigIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("year",)},
        ),
    ]
