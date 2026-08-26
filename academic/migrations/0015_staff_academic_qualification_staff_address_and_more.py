from django.db import migrations, models


def populate_staff_from_teachers(apps, schema_editor):
    Staff = apps.get_model("academic", "Staff")
    Teacher = apps.get_model("academic", "Teacher")

    for teacher in Teacher.objects.all():
        staff = None
        if teacher.staff_id:
            staff = Staff.objects.filter(pk=teacher.staff_id).first()
        elif teacher.user_id:
            staff = Staff.objects.filter(user_id=teacher.user_id).first()
            if staff:
                teacher.staff_id = staff.pk
                teacher.save(update_fields=["staff"])

        if staff:
            updated_fields = []
            if not staff.address and getattr(teacher, "address", ""):
                staff.address = teacher.address
                updated_fields.append("address")
            if not staff.designation and getattr(teacher, "designation", ""):
                staff.designation = teacher.designation
                updated_fields.append("designation")
            if updated_fields:
                staff.save(update_fields=updated_fields)


def reverse_populate(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("academic", "0014_expand_admission_number_lengths"),
    ]

    operations = [
        migrations.AddField(
            model_name="staff",
            name="academic_qualification",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="staff",
            name="address",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="staff",
            name="date_of_birth",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="staff",
            name="salary",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=12, null=True
            ),
        ),
        migrations.AddField(
            model_name="staff",
            name="state",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.RunPython(populate_staff_from_teachers, reverse_populate),
    ]
