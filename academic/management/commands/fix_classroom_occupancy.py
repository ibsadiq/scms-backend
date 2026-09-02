from django.core.management.base import BaseCommand
from django.db import transaction
from django_tenants.utils import schema_context
from tenants.models import Client


class Command(BaseCommand):
    help = "Recalculates and fixes classroom occupied_sits across tenant schemas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            type=str,
            default=None,
            help="Specify a single tenant schema (e.g. 'standard'). Defaults to all tenant schemas.",
        )

    def handle(self, *args, **options):
        schema_name = options.get("schema")

        if schema_name:
            target_tenants = Client.objects.filter(schema_name=schema_name)
            if not target_tenants.exists():
                self.stderr.write(self.style.ERROR(f"Tenant schema '{schema_name}' does not exist."))
                return
        else:
            target_tenants = Client.objects.exclude(schema_name="public").order_by("schema_name")

        total_fixed = 0
        tenant_count = 0

        for tenant in target_tenants:
            tenant_count += 1
            s_name = tenant.schema_name
            with schema_context(s_name):
                from academic.models import ClassRoom, Student, StudentClassEnrollment
                from administration.models import AcademicYear

                active_year = AcademicYear.objects.filter(active_year=True).first()
                active_year_name = active_year.name if active_year else "None"
                self.stdout.write(f"\n--- Tenant Schema: {s_name} (Active Year: {active_year_name}) ---")

                classrooms = ClassRoom.objects.all().order_by("id")
                if not classrooms.exists():
                    self.stdout.write(f"  No classrooms found in '{s_name}'.")
                    continue

                updated_in_schema = 0
                with transaction.atomic():
                    for classroom in classrooms:
                        direct_count = Student.objects.filter(classroom=classroom, is_active=True).count()

                        if active_year:
                            enrollment_count = StudentClassEnrollment.objects.filter(
                                classroom=classroom,
                                academic_year=active_year,
                                is_active=True,
                                student__is_active=True,
                            ).count()
                            actual_occupancy = enrollment_count if enrollment_count > 0 else direct_count
                        else:
                            actual_occupancy = direct_count

                        if classroom.occupied_sits != actual_occupancy:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"  [FIX] {classroom.name} (ID: {classroom.id}): "
                                    f"{classroom.occupied_sits} -> {actual_occupancy} "
                                    f"(Capacity: {classroom.capacity})"
                                )
                            )
                            classroom.occupied_sits = actual_occupancy
                            classroom.save(update_fields=["occupied_sits"])
                            updated_in_schema += 1
                        else:
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"  [OK]  {classroom.name} (ID: {classroom.id}): "
                                    f"occupied_sits={classroom.occupied_sits}"
                                )
                            )

                self.stdout.write(f"  Corrected {updated_in_schema} classroom(s) in schema '{s_name}'.")
                total_fixed += updated_in_schema

        self.stdout.write(
            self.style.SUCCESS(
                f"\nFinished! Processed {tenant_count} tenant(s). Fixed occupancy for {total_fixed} classroom(s)."
            )
        )
