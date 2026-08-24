from pathlib import Path

from django.test import SimpleTestCase


class AttendanceWritePathClosureTests(SimpleTestCase):
    def test_request_application_code_has_no_direct_daily_row_writes(self):
        root = Path(__file__).resolve().parent.parent
        mutation_tokens = (
            "StudentAttendance.objects.create(",
            "StudentAttendance.objects.update_or_create(",
            "StudentAttendance.objects.bulk_create(",
            "StaffAttendance.objects.create(",
            "StaffAttendance.objects.update_or_create(",
            "StaffAttendance.objects.bulk_create(",
        )
        offenders = []
        for app_name in ("academic", "administration", "api", "attendance", "examination", "sis", "users"):
            for path in (root / app_name).rglob("*.py"):
                if (
                    "migrations" in path.parts
                    or "management" in path.parts
                    or "services" in path.parts
                    or path.name.startswith("test")
                    or "tests" in path.parts
                ):
                    continue
                text = path.read_text(errors="ignore")
                if any(token in text for token in mutation_tokens):
                    offenders.append(str(path.relative_to(root)))
        self.assertEqual(offenders, [])

