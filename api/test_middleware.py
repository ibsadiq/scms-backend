from django.db import IntegrityError
from django.test import RequestFactory, SimpleTestCase

from api.middleware import CustomExceptionMiddleware


class DatabaseErrorSanitizationTests(SimpleTestCase):
    def test_integrity_error_does_not_expose_database_details(self):
        leaked_detail = 'duplicate key violates constraint "secret_constraint" in schema private'

        def fail(_request):
            raise IntegrityError(leaked_detail)

        response = CustomExceptionMiddleware(fail)(RequestFactory().post("/api/test/"))
        body = response.content.decode()
        self.assertEqual(response.status_code, 409)
        self.assertNotIn("secret_constraint", body)
        self.assertNotIn("private", body)

