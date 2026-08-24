from pathlib import Path

from django.test import SimpleTestCase


class FinanceClosureStaticTests(SimpleTestCase):
    def test_application_code_does_not_bulk_create_allocations(self):
        root = Path(__file__).resolve().parent.parent
        offenders = []
        for path in root.rglob("*.py"):
            if "migrations" in path.parts or path.name.startswith("test"):
                continue
            if "FeePaymentAllocation.objects.bulk_create" in path.read_text(errors="ignore"):
                offenders.append(str(path.relative_to(root)))
        self.assertEqual(offenders, [])
