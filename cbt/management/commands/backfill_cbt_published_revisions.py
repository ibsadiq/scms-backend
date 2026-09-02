from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from cbt.models import CBTExam, CBTExamStatus
from cbt.services import PublishedExamRevisionService


class Command(BaseCommand):
    help = (
        "Create immutable revisions for legacy published CBT exams in the current "
        "tenant schema. Run through django-tenants tenant_command/migrate_schemas."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        schema_name = getattr(connection, "schema_name", None)
        if not schema_name or schema_name == "public":
            raise CommandError(
                "Select a tenant schema (for example with tenant_command) before backfilling."
            )

        exams = CBTExam.objects.filter(
            status=CBTExamStatus.PUBLISHED,
            published_revisions__isnull=True,
        ).order_by("pk")
        count = exams.count()
        if options["dry_run"]:
            self.stdout.write(f"{schema_name}: {count} exam(s) require a revision.")
            return

        created = 0
        for exam in exams.iterator():
            PublishedExamRevisionService.ensure_current_for_exam(exam)
            created += 1
        self.stdout.write(self.style.SUCCESS(
            f"{schema_name}: created {created} immutable published revision(s)."
        ))
