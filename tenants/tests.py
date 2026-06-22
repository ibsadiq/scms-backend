from django.test import TestCase, RequestFactory
from django.http import HttpResponse
from django.db import connection

from tenants.tenant_header_middleware import TenantHeaderMiddleware
from tenants.models import Client as TenantClient


class TenantHeaderMiddlewareTests(TestCase):
    def setUp(self):
        # ensure public exists
        self.public = TenantClient.objects.get(schema_name='public')
        # create a secondary tenant if not present
        self.school1, _ = TenantClient.objects.get_or_create(
            schema_name='school1',
            defaults={
                'name': 'School 1',
                'domain_url': 'school1.test',
                'paid_until': '2099-01-01',
                'on_trial': False,
            },
        )
        # middleware using simple passthrough response
        self.middleware = TenantHeaderMiddleware(lambda req: HttpResponse('ok'))
        self.factory = RequestFactory()

    def test_switch_tenant_with_header(self):
        request = self.factory.get('/', HTTP_X_TENANT_SLUG='school1')
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)
        # connection should now use school1 schema
        self.assertEqual(connection.schema_name, 'school1')

    def test_invalid_tenant_header(self):
        request = self.factory.get('/', HTTP_X_TENANT_SLUG='invalid')
        response = self.middleware(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Invalid Tenant", response.content)
        # schema should remain public
        self.assertEqual(connection.schema_name, 'public')
