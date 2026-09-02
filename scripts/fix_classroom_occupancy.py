#!/usr/bin/env python
"""
Script / Command to recalculate and fix classroom occupied_sits across tenant schemas.
Can be run directly:
    python scripts/fix_classroom_occupancy.py
    python scripts/fix_classroom_occupancy.py --schema=standard
Or via manage.py runscript:
    python manage.py runscript fix_classroom_occupancy
"""
import argparse
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "school.settings")

import django
if not django.apps.apps.ready:
    django.setup()

from django.db import transaction
from django.db.models import Count, Q
from django_tenants.utils import schema_context
from tenants.models import Client


def fix_occupancy_for_schema(schema_name: str) -> int:
    """Fix classroom occupancies for a specific tenant schema."""
    with schema_context(schema_name):
        from academic.models import ClassRoom, Student, StudentClassEnrollment
        from administration.models import AcademicYear

        active_year = AcademicYear.objects.filter(active_year=True).first()
        active_year_name = active_year.name if active_year else "None"
        print(f"\n--- Processing Schema: {schema_name} (Active Academic Year: {active_year_name}) ---")

        classrooms = ClassRoom.objects.all().order_by("id")
        if not classrooms.exists():
            print(f"No classrooms found in schema '{schema_name}'.")
            return 0

        updated_count = 0
        with transaction.atomic():
            for classroom in classrooms:
                # Count 1: Active students directly linked to this classroom
                direct_students_count = Student.objects.filter(
                    classroom=classroom,
                    is_active=True
                ).count()

                # Count 2: Active enrollments in active academic year
                if active_year:
                    enrollment_count = StudentClassEnrollment.objects.filter(
                        classroom=classroom,
                        academic_year=active_year,
                        is_active=True,
                        student__is_active=True
                    ).count()
                    # Authoritative occupancy is active enrollment if present, otherwise direct student count
                    actual_occupancy = enrollment_count if enrollment_count > 0 else direct_students_count
                else:
                    actual_occupancy = direct_students_count

                if classroom.occupied_sits != actual_occupancy:
                    print(
                        f"  [FIX] Classroom '{classroom.name}' (ID: {classroom.id}): "
                        f"occupied_sits {classroom.occupied_sits} -> {actual_occupancy} "
                        f"(Capacity: {classroom.capacity})"
                    )
                    classroom.occupied_sits = actual_occupancy
                    classroom.save(update_fields=["occupied_sits"])
                    updated_count += 1
                else:
                    print(
                        f"  [OK]  Classroom '{classroom.name}' (ID: {classroom.id}): "
                        f"occupied_sits={classroom.occupied_sits} (matches actual count {actual_occupancy})"
                    )

        print(f"Schema '{schema_name}' summary: {updated_count} classrooms corrected.")
        return updated_count


def run(*args):
    """Entry point for django-extensions runscript or direct execution."""
    parser = argparse.ArgumentParser(description="Recalculate classroom occupancies across tenant schemas.")
    parser.add_argument("--schema", type=str, default=None, help="Specific tenant schema name to process (e.g. 'standard').")
    
    parsed_args, _ = parser.parse_known_args(args=list(args) if args else sys.argv[1:])

    print("==================================================")
    print("RECALCULATING CLASSROOM OCCUPANCIES")
    print("==================================================")

    if parsed_args.schema:
        target_tenants = Client.objects.filter(schema_name=parsed_args.schema)
        if not target_tenants.exists():
            print(f"Error: Tenant schema '{parsed_args.schema}' does not exist.")
            return
    else:
        target_tenants = Client.objects.exclude(schema_name="public").order_by("schema_name")

    total_fixed = 0
    tenant_count = 0
    for tenant in target_tenants:
        tenant_count += 1
        total_fixed += fix_occupancy_for_schema(tenant.schema_name)

    print("\n==================================================")
    print(f"COMPLETED! Processed {tenant_count} tenant(s). Total classrooms fixed: {total_fixed}.")
    print("==================================================")


if __name__ == "__main__":
    run()
