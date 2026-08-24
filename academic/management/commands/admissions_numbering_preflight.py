import re
from collections import Counter

from django.core.management.base import BaseCommand

from academic.models import AdmissionApplication, Student


class Command(BaseCommand):
    help = "Read-only inventory of historical Student and admission-application numbers."

    def handle(self, *args, **options):
        self._report("Student", Student.objects.values_list("admission_number", flat=True))
        self._report(
            "Admission application",
            AdmissionApplication.objects.values_list("application_number", flat=True),
        )

    def _report(self, label, values):
        values = list(values)
        populated = [value for value in values if value]
        duplicates = sorted(value for value, count in Counter(populated).items() if count > 1)
        malformed = [value for value in populated if not re.search(r"\d+$", value)]
        suffixes = [int(match.group()) for value in populated if (match := re.search(r"\d+$", value))]
        self.stdout.write(f"{label} numbers:")
        self.stdout.write(f"  total={len(values)} populated={len(populated)} blank={len(values) - len(populated)}")
        self.stdout.write(f"  duplicates={duplicates or 'none'}")
        self.stdout.write(f"  malformed_suffix_count={len(malformed)}")
        self.stdout.write(f"  maximum_numeric_suffix={max(suffixes, default=0)}")
