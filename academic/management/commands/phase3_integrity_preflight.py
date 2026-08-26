import re

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Q
from django_tenants.utils import get_public_schema_name, schema_context

from tenants.models import Client


class Command(BaseCommand):
    help = "Read-only tenant preflight for Phase 3 ID-card, admission, and enrollment constraints."

    def handle(self, *args, **options):
        schemas = list(
            Client.objects.exclude(schema_name=get_public_schema_name())
            .order_by("schema_name").values_list("schema_name", flat=True)
        )
        conflict_count = 0
        for schema_name in schemas:
            self.stdout.write(f"SCHEMA {schema_name}")
            with schema_context(schema_name):
                conflict_count += self._active_card_conflicts()
                conflict_count += self._admission_conflicts()
                conflict_count += self._enrollment_conflicts()
        if conflict_count:
            raise CommandError(
                f"Phase 3 preflight found {conflict_count} conflict(s); no data was changed."
            )
        self.stdout.write(self.style.SUCCESS(
            f"Phase 3 preflight PASS across {len(schemas)} tenant schema(s); no data was changed."
        ))

    def _active_card_conflicts(self):
        from idcards.models import IDCard

        count = 0
        for holder_field in ("student_id", "staff_id"):
            rows = list(
                IDCard.objects.filter(status="ACTIVE", **{f"{holder_field}__isnull": False})
                .values(holder_field).annotate(active_count=Count("id"))
                .filter(active_count__gt=1).order_by(holder_field)
            )
            self.stdout.write(f"  active-card {holder_field}: {len(rows)} conflict(s)")
            for row in rows:
                self.stdout.write(f"    {row}")
            count += len(rows)
        return count

    def _admission_conflicts(self):
        from academic.models import Student

        duplicates = list(
            Student.objects.values("admission_number").annotate(row_count=Count("id"))
            .filter(row_count__gt=1).order_by("admission_number")
        )
        malformed = [
            {"id": pk, "admission_number": number}
            for pk, number in Student.objects.order_by("pk").values_list("pk", "admission_number")
            if not re.fullmatch(r"ADM-\d{4}-\d+", number or "")
        ]
        self.stdout.write(f"  admission duplicates: {len(duplicates)} conflict(s)")
        for row in duplicates:
            self.stdout.write(f"    {row}")
        self.stdout.write(f"  admission malformed: {len(malformed)} conflict(s)")
        for row in malformed:
            self.stdout.write(f"    {row}")
        return len(duplicates) + len(malformed)

    def _enrollment_conflicts(self):
        from academic.models import Student, StudentClassEnrollment

        conflicts = []
        enrollments = StudentClassEnrollment.objects.filter(
            is_active=True, academic_year__active_year=True
        ).select_related("student", "classroom__grade_level").order_by("student_id", "academic_year_id")
        for enrollment in enrollments:
            student = enrollment.student
            if student.classroom_id != enrollment.classroom_id:
                conflicts.append({
                    "enrollment_id": enrollment.pk,
                    "student_id": enrollment.student_id,
                    "enrollment_classroom_id": enrollment.classroom_id,
                    "student_classroom_id": student.classroom_id,
                })
        multiple = list(
            StudentClassEnrollment.objects.filter(
                is_active=True, academic_year__active_year=True
            ).values("student_id").annotate(row_count=Count("id"))
            .filter(row_count__gt=1).order_by("student_id")
        )
        orphan_snapshots = list(
            Student.objects.filter(classroom__isnull=False)
            .exclude(student_classes__is_active=True, student_classes__academic_year__active_year=True)
            .order_by("pk").values("id", "classroom_id")
        )
        self.stdout.write(f"  enrollment snapshot divergence: {len(conflicts)} conflict(s)")
        for row in conflicts:
            self.stdout.write(f"    {row}")
        self.stdout.write(f"  multiple active current enrollments: {len(multiple)} conflict(s)")
        for row in multiple:
            self.stdout.write(f"    {row}")
        self.stdout.write(f"  snapshots without active current enrollment: {len(orphan_snapshots)} conflict(s)")
        for row in orphan_snapshots:
            self.stdout.write(f"    {row}")
        return len(conflicts) + len(multiple) + len(orphan_snapshots)
