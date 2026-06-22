from django.test import TestCase, Client
from django_tenants.utils import schema_context
from tenants.models import Client as TenantClient
from users.models import CustomUser as User


class AuthTenantTests(TestCase):
    def setUp(self):
        # create a tenant for login tests
        self.school, _ = TenantClient.objects.get_or_create(
            schema_name='school2',
            defaults={
                'name': 'School 2',
                'domain_url': 'school2.test',
                'paid_until': '2099-01-01',
                'on_trial': False,
            },
        )
        # create a user inside that tenant
        with schema_context('school2'):
            self.user = User.objects.create_user(
                email='teacher@school2.test',
                password='secret123',
                is_staff=True,
            )
        self.client = Client()

    def test_login_with_tenant_header(self):
        response = self.client.post(
            '/api/users/login/',
            {'email': 'teacher@school2.test', 'password': 'secret123'},
            content_type='application/json',
            HTTP_X_TENANT_SLUG='school2',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('access', data)
        self.assertEqual(data.get('tenant_slug'), 'school2')
        # tenant user shouldn't be flagged as super-admin
        self.assertFalse(data.get('isSuperAdmin', False))

    def test_login_without_header_defaults_public(self):
        # logging in without header should try public schema and fail
        response = self.client.post(
            '/api/users/login/',
            {'email': 'teacher@school2.test', 'password': 'secret123'},
            content_type='application/json',
        )
        self.assertNotEqual(response.status_code, 200)

    def test_admin_login_public_slug(self):
        # create a superuser in the public schema
        with schema_context('public'):
            User.objects.create_superuser(email='super@public.test', password='supeR123')
        response = self.client.post(
            '/api/users/login/',
            {'email': 'super@public.test', 'password': 'supeR123'},
            content_type='application/json',
            HTTP_X_TENANT_SLUG='public',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('tenant_slug'), 'public')
        # should be marked as a platform-level admin
        self.assertTrue(data.get('isSuperAdmin'))
