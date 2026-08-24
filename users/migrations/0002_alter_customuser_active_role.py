from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="customuser",
            name="active_role",
            field=models.CharField(
                blank=True,
                choices=[
                    ("admin", "Admin"),
                    ("teacher", "Teacher"),
                    ("parent", "Parent"),
                    ("student", "Student"),
                    ("accountant", "Accountant"),
                    ("staff", "Staff"),
                ],
                help_text="Currently active role for users with multiple roles",
                max_length=20,
                null=True,
            ),
        ),
    ]
