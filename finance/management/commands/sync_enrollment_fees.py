import logging
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Q
from django_tenants.utils import schema_context

from academic.models import ClassRoom, Student, StudentClassEnrollment
from administration.models import AcademicYear, Term
from finance.services.fee_assignment_service import FeeAssignmentService
from tenants.models import Client

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Synchronize and backfill fee assignments from authoritative StudentClassEnrollment records "
        "for a specific tenant schema and academic year."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            type=str,
            default=None,
            help="Tenant schema name to execute against (e.g. 'cherville_montessori_international_school').",
        )
        parser.add_argument(
            "--academic-year",
            type=str,
            default=None,
            help="Academic year name or ID (e.g. '2026/2027'). Defaults to the active academic year.",
        )
        parser.add_argument(
            "--term",
            type=str,
            default=None,
            help="Optional term name or ID to target. Defaults to the academic year's effective term.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Perform a dry run without creating or modifying any database records.",
        )
        parser.add_argument(
            "--student-id",
            type=str,
            default=None,
            help="Filter by student ID, admission number, or global student_id.",
        )
        parser.add_argument(
            "--classroom-id",
            type=str,
            default=None,
            help="Filter by classroom ID or classroom name.",
        )

    def handle(self, *args, **options):
        schema_name = options.get("schema")
        current_connection_schema = getattr(connection, "schema_name", None)

        if schema_name:
            if not Client.objects.filter(schema_name=schema_name).exists():
                raise CommandError(f"Tenant schema '{schema_name}' does not exist.")
            with schema_context(schema_name):
                self._execute_sync(options, schema_name)
        elif current_connection_schema and current_connection_schema != "public":
            self._execute_sync(options, current_connection_schema)
        else:
            raise CommandError(
                "A tenant schema must be specified via --schema=<schema_name> "
                "or by running via 'python manage.py tenant_command sync_enrollment_fees --schema=<schema_name>'."
            )

    def _execute_sync(self, options, active_schema):
        dry_run = options.get("dry_run", False)
        academic_year_arg = options.get("academic_year")
        term_arg = options.get("term")
        student_arg = options.get("student_id")
        classroom_arg = options.get("classroom_id")

        # 1. Resolve Academic Year
        if academic_year_arg:
            academic_year_arg_clean = str(academic_year_arg).strip()
            academic_year = AcademicYear.objects.filter(name__iexact=academic_year_arg_clean).first()
            if not academic_year and academic_year_arg_clean.isdigit():
                academic_year = AcademicYear.objects.filter(pk=int(academic_year_arg_clean)).first()
            if not academic_year:
                raise CommandError(
                    f"Academic year '{academic_year_arg}' not found in schema '{active_schema}'."
                )
        else:
            academic_year = AcademicYear.objects.filter(active_year=True).first()
            if not academic_year:
                raise CommandError(
                    f"No active academic year found in schema '{active_schema}'. "
                    f"Please specify an academic year with --academic-year."
                )

        # 2. Resolve optional Term filter if passed
        target_term = None
        if term_arg:
            term_arg_clean = str(term_arg).strip()
            target_term = Term.objects.filter(
                academic_year=academic_year,
                name__iexact=term_arg_clean,
            ).first()
            if not target_term and term_arg_clean.isdigit():
                target_term = Term.objects.filter(
                    academic_year=academic_year,
                    pk=int(term_arg_clean),
                ).first()
            if not target_term:
                raise CommandError(
                    f"Term '{term_arg}' not found for academic year '{academic_year.name}' in schema '{active_schema}'."
                )

        # 3. Query active enrollments for this academic year
        enrollments_qs = StudentClassEnrollment.objects.filter(
            academic_year=academic_year,
            is_active=True,
        ).select_related(
            "student",
            "classroom",
            "classroom__grade_level",
            "academic_year",
        )

        # 4. Apply student filter if provided
        if student_arg:
            student_arg_clean = str(student_arg).strip()
            student_filter = (
                Q(student__admission_number__iexact=student_arg_clean)
                | Q(student__student_id__iexact=student_arg_clean)
            )
            if student_arg_clean.isdigit():
                student_filter |= Q(student__pk=int(student_arg_clean))
            enrollments_qs = enrollments_qs.filter(student_filter)

        # 5. Apply classroom filter if provided
        if classroom_arg:
            classroom_arg_clean = str(classroom_arg).strip()
            classroom_filter = Q(classroom__name__iexact=classroom_arg_clean)
            if classroom_arg_clean.isdigit():
                classroom_filter |= Q(classroom__pk=int(classroom_arg_clean))
            enrollments_qs = enrollments_qs.filter(classroom_filter)

        enrollments_qs = enrollments_qs.order_by(
            "classroom__name",
            "student__admission_number",
            "pk",
        )

        # 6. Process enrollments
        enrollments_scanned = 0
        applicable_assignments_found = 0
        assignments_would_be_created = 0
        assignments_created = 0
        assignments_already_existing = 0
        skipped_enrollments = 0
        skipped_reasons = []
        errors = []

        mode_str = "DRY RUN (zero database writes)" if dry_run else "LIVE RUN (assignments written to DB)"
        self.stdout.write(f"\nStarting fee sync for schema '{active_schema}' [{mode_str}]...")
        self.stdout.write(f"Academic Year: {academic_year.name}")
        if target_term:
            self.stdout.write(f"Target Term:   {target_term.name}")

        for enrollment in enrollments_qs.iterator(chunk_size=500):
            enrollments_scanned += 1
            student = enrollment.student
            student_desc = (
                f"{student.full_name} "
                f"(ID: {student.pk}, Adm: {student.admission_number or 'N/A'})"
                if student
                else f"Enrollment #{enrollment.pk} (No Student)"
            )

            try:
                details = FeeAssignmentService.sync_fees_for_enrollment(
                    enrollment=enrollment,
                    term=target_term,
                    dry_run=dry_run,
                    return_details=True,
                )

                if details.get("skipped"):
                    skipped_enrollments += 1
                    reason = details.get("skip_reason") or "Unknown"
                    skipped_reasons.append(f"Enrollment #{enrollment.pk} [{student_desc}]: {reason}")
                else:
                    applicable_assignments_found += details.get("applicable_count", 0)
                    assignments_already_existing += details.get("existing_count", 0)
                    if dry_run:
                        assignments_would_be_created += details.get("would_create_count", 0)
                    else:
                        assignments_created += details.get("created_count", 0)

                    if details.get("errors"):
                        for err in details["errors"]:
                            error_msg = f"Enrollment #{enrollment.pk} [{student_desc}]: {err}"
                            errors.append(error_msg)
                            self.stderr.write(self.style.ERROR(f"  ERROR: {error_msg}"))

            except Exception as exc:
                error_msg = f"Enrollment #{enrollment.pk} [{student_desc}]: {type(exc).__name__}: {str(exc)}"
                errors.append(error_msg)
                self.stderr.write(self.style.ERROR(f"  ERROR: {error_msg}"))
                logger.exception("Error syncing fees for enrollment %s", enrollment.pk)

        # 7. Print summary report
        banner_title = "Fee Assignment Backfill Summary (Dry Run)" if dry_run else "Fee Assignment Backfill Summary"
        self.stdout.write("")
        self.stdout.write("=" * 60)
        self.stdout.write(banner_title)
        self.stdout.write("=" * 60)
        self.stdout.write(f"Tenant Schema:                     {active_schema}")
        self.stdout.write(f"Academic Year:                     {academic_year.name}")
        if target_term:
            self.stdout.write(f"Target Term:                       {target_term.name}")
        self.stdout.write(f"Mode:                              {mode_str}")
        self.stdout.write("-" * 60)
        self.stdout.write(f"Enrollments scanned:               {enrollments_scanned}")
        self.stdout.write(f"Applicable assignments found:      {applicable_assignments_found}")
        self.stdout.write(f"Assignments that would be created: {assignments_would_be_created}")
        self.stdout.write(f"Assignments created:               {assignments_created}")
        self.stdout.write(f"Assignments already existing:      {assignments_already_existing}")
        self.stdout.write(f"Skipped enrollments:               {skipped_enrollments}")
        self.stdout.write(f"Errors:                            {len(errors)}")
        self.stdout.write("=" * 60)

        if skipped_reasons:
            self.stdout.write("\nSkipped Enrollments Detail:")
            for item in skipped_reasons[:20]:
                self.stdout.write(f"  - {item}")
            if len(skipped_reasons) > 20:
                self.stdout.write(f"  ... and {len(skipped_reasons) - 20} more")

        if errors:
            self.stdout.write(self.style.ERROR(f"\nErrors Detail ({len(errors)} total):"))
            for item in errors:
                self.stdout.write(self.style.ERROR(f"  - {item}"))
            self.stdout.write("")
            raise CommandError(
                f"Sync completed with {len(errors)} error(s). Please inspect the errors above."
            )

        self.stdout.write(self.style.SUCCESS("Fee synchronization complete.\n"))
