from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase
from django.urls import Resolver404, resolve
from drf_spectacular.generators import SchemaGenerator

from api.jobs.serializers import BackgroundJobSerializer
from notifications.serializers import DirectMessageSerializer


class Phase4BRouteContractTests(SimpleTestCase):
    def test_public_admissions_method_and_identifier_contract(self):
        collection = resolve("/api/public/admissions/applications/")
        self.assertEqual(collection.func.actions, {"post": "create"})

        document = resolve(
            "/api/public/admissions/applications/token/documents/"
            "6e4445d4-a1f3-46b5-8789-84ff04e9b273/"
        )
        self.assertEqual(document.func.actions, {"delete": "destroy"})
        with self.assertRaises(Resolver404):
            resolve("/api/public/admissions/documents/1/")

    def test_message_and_job_methods_are_narrow(self):
        messages = resolve("/api/notifications/messages/")
        self.assertEqual(messages.func.actions["get"], "list")
        self.assertEqual(messages.func.actions["post"], "create")
        for method in ("put", "patch", "delete"):
            self.assertNotIn(method, messages.func.actions)

        detail = resolve("/api/notifications/messages/1/")
        self.assertEqual(detail.func.actions["get"], "retrieve")
        for method in ("post", "put", "patch", "delete"):
            self.assertNotIn(method, detail.func.actions)

        job = resolve("/api/jobs/6e4445d4-a1f3-46b5-8789-84ff04e9b273/")
        self.assertEqual(job.url_name, "detail")
        self.assertTrue(hasattr(job.func.view_class, "get"))
        for method in ("post", "put", "patch", "delete"):
            self.assertFalse(hasattr(job.func.view_class, method))

        with self.assertRaises(Resolver404):
            resolve("/api/tasks/arbitrary-celery-id/")

    def test_sensitive_fields_are_not_frontend_contracts(self):
        self.assertNotIn("celery_task_id", BackgroundJobSerializer().fields)
        message_fields = DirectMessageSerializer().fields
        for field in ("sender_email", "recipient_email", "password", "token"):
            self.assertNotIn(field, message_fields)

    def test_resolver_inventory_command_runs(self):
        output = StringIO()
        call_command("api_route_inventory", stdout=output, verbosity=0)
        self.assertIn('"classification": "canonical"', output.getvalue())


class Phase4BSchemaContractTests(SimpleTestCase):
    def assert_json_schema(self, operation, status_code):
        response = operation["responses"][str(status_code)]
        self.assertIn("schema", response["content"]["application/json"])

    def test_phase4a_canonical_routes_are_in_schema(self):
        schema = SchemaGenerator().get_schema(request=None, public=True)
        paths = schema["paths"]
        self.assertIn("/api/jobs/{public_id}/", paths)
        self.assertNotIn("/api/tasks/{task_id}/", paths)
        self.assertIn("/api/reports/academic/", paths)
        self.assertIn("/api/notifications/messages/recipients/", paths)
        self.assertIn("/api/public/admissions/applications/", paths)
        self.assertNotIn("/api/celery/health/", paths)

        application = paths["/api/public/admissions/applications/"]
        self.assertEqual(set(application), {"post"})

    def test_composite_routes_have_explicit_schemas(self):
        schema = SchemaGenerator().get_schema(request=None, public=True)
        paths = schema["paths"]
        operations = (
            ("/api/academic/teachers/my-classes/", "get", 200),
            ("/api/academic/classrooms/{classroom_id}/students/", "get", 200),
            ("/api/academic/timetable/my-schedule/", "get", 200),
            ("/api/administration/dashboard/", "get", 200),
            ("/api/attendance/class/{classroom_id}/summary/", "get", 200),
            ("/api/attendance/device-scans/", "post", 200),
            ("/api/cbt/grading/manual/pending/", "get", 200),
            ("/api/cbt/grading/manual/{id}/grade/", "post", 200),
            ("/api/core/lookup/student/", "get", 200),
            ("/api/core/transfers/complete/", "post", 200),
            ("/api/finance/dashboard/summary/", "get", 200),
            ("/api/finance/parent/fees/", "get", 200),
            ("/api/idcards/template-fields/", "get", 200),
            ("/api/sis/students/bulk-upload/", "post", 201),
            ("/api/tenants/branding/", "get", 200),
            ("/api/tenants/school/settings/", "patch", 200),
            ("/api/tenants/search/", "get", 200),
            ("/api/timetable/generate-timetable/", "post", 200),
            ("/api/users/parent/children/", "get", 200),
            ("/api/users/parent/dashboard/", "get", 200),
            ("/api/users/teacher/dashboard/", "get", 200),
            ("/api/users/teachers/bulk-upload/", "post", 201),
        )
        for path, method, status_code in operations:
            with self.subTest(path=path, method=method):
                self.assert_json_schema(paths[path][method], status_code)
