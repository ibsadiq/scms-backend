from django.conf import settings
from django.test import Client, SimpleTestCase
from django.urls import reverse
from school.testcases import TenantTestCase
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from tenants.models import Client as TenantClient, Domain, TenantStatus
from users.models import CustomUser as User
from users.authentication import TenantBoundJWTAuthentication
from users.tokens import tenant_refresh_token_for_user
from users.views import (
    AcceptInvitationView,
    MyTokenObtainPairView,
    MyTokenRefreshSerializer,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    ValidateInvitationView,
)


class AuthTenantTests(TenantTestCase):
    @classmethod
    def get_test_schema_name(cls):
        return 'school2'

    @classmethod
    def get_test_tenant_domain(cls):
        return f"school2.{settings.BASE_DOMAIN}"

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.name = 'School 2'
        tenant.status = TenantStatus.ACTIVE
        return tenant

    @classmethod
    def setup_domain(cls, domain):
        domain.is_primary = True
        return domain

    def setUp(self):
        self.school = self.tenant
        self.public_schema_name = get_public_schema_name()
        with schema_context(self.public_schema_name):
            self.public_tenant, _ = TenantClient.objects.get_or_create(
                schema_name=self.public_schema_name,
                defaults={
                    'name': 'SSync Platform',
                    'status': TenantStatus.ACTIVE,
                },
            )
            self.public_domain, _ = Domain.objects.get_or_create(
                domain=settings.BASE_DOMAIN,
                defaults={
                    'tenant': self.public_tenant,
                    'is_primary': True,
                },
            )
        # create a user inside that tenant
        with schema_context(self.school.schema_name):
            self.user = User.objects.create_user(
                email='teacher@school2.test',
                password='secret123',
                is_staff=True,
            )
        self.client = Client(HTTP_HOST=self.public_domain.domain)
        self.login_url = reverse('token_obtain_pair')

    def test_login_with_tenant_header(self):
        response = self.client.post(
            self.login_url,
            {'email': 'teacher@school2.test', 'password': 'secret123'},
            content_type='application/json',
            HTTP_X_TENANT_SLUG='school2',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('access', data)
        self.assertEqual(data.get('tenant_slug'), 'school2')
        self.assertEqual(AccessToken(data['access'])['tenant_slug'], 'school2')
        self.assertEqual(RefreshToken(data['refresh'])['tenant_slug'], 'school2')
        # tenant user shouldn't be flagged as super-admin
        self.assertFalse(data.get('isSuperAdmin', False))

    def test_login_without_header_defaults_public(self):
        # logging in without header should try public schema and fail
        response = self.client.post(
            self.login_url,
            {'email': 'teacher@school2.test', 'password': 'secret123'},
            content_type='application/json',
        )
        self.assertNotEqual(response.status_code, 200)

    def test_admin_login_on_public_host(self):
        # create a superuser in the public schema
        with schema_context(self.public_schema_name):
            User.objects.create_superuser(email='super@public.test', password='supeR123')
        response = self.client.post(
            self.login_url,
            {'email': 'super@public.test', 'password': 'supeR123'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('tenant_slug'), 'public')
        # should be marked as a platform-level admin
        self.assertTrue(data.get('isSuperAdmin'))

    def test_refresh_rejects_token_from_another_schema(self):
        with schema_context(self.school.schema_name):
            token = tenant_refresh_token_for_user(self.user)

        with schema_context(self.public_schema_name):
            serializer = MyTokenRefreshSerializer(data={'refresh': str(token)})
            self.assertFalse(serializer.is_valid())
            self.assertIn('refresh', serializer.errors)

    def test_authentication_rejects_access_token_from_another_schema(self):
        with schema_context(self.school.schema_name):
            token = tenant_refresh_token_for_user(self.user).access_token

        with schema_context(self.public_schema_name):
            with self.assertRaises(AuthenticationFailed):
                TenantBoundJWTAuthentication().get_user(token)

    def test_refresh_rejects_legacy_token_without_tenant_claim(self):
        with schema_context(self.school.schema_name):
            token = RefreshToken.for_user(self.user)
            serializer = MyTokenRefreshSerializer(data={'refresh': str(token)})
            self.assertFalse(serializer.is_valid())
            self.assertIn('refresh', serializer.errors)


class AuthenticationDefaultsTests(SimpleTestCase):
    def test_default_permission_requires_authentication(self):
        self.assertEqual(
            settings.REST_FRAMEWORK['DEFAULT_PERMISSION_CLASSES'],
            ['rest_framework.permissions.IsAuthenticated'],
        )

    def test_authentication_uses_tenant_bound_backend(self):
        self.assertEqual(
            settings.REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES'],
            ('users.authentication.TenantBoundJWTAuthentication',),
        )

    def test_intended_user_endpoints_remain_explicitly_public(self):
        public_views = (
            MyTokenObtainPairView,
            ValidateInvitationView,
            AcceptInvitationView,
            PasswordResetRequestView,
            PasswordResetConfirmView,
        )
        for view in public_views:
            self.assertEqual(view.permission_classes, [AllowAny])
