import re
from hashlib import sha1

from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.test import TransactionTestCase
from django_tenants.test.cases import TenantTestCase as DjangoTenantTestCase
from django_tenants.utils import (
    get_public_schema_name,
    get_tenant_domain_model,
    get_tenant_model,
    schema_exists,
)


class TenantTestCaseMixin:
    """Class-unique django-tenants fixture naming and lifecycle helpers."""

    tenant = None
    domain = None

    @classmethod
    def _test_identity(cls):
        return f"{cls.__module__}.{cls.__qualname__}"

    @classmethod
    def get_test_schema_name(cls):
        readable = re.sub(r"[^a-z0-9]+", "_", cls.__name__.lower()).strip("_")
        digest = sha1(cls._test_identity().encode()).hexdigest()[:10]
        # PostgreSQL identifiers are limited to 63 bytes. This is ASCII-only.
        return f"test_{readable[:46]}_{digest}"

    @classmethod
    def get_test_tenant_domain(cls):
        # The schema name is <= 62 characters, so its hostname label is valid.
        return f"{cls.get_test_schema_name().replace('_', '-')}.test"

    @classmethod
    def get_verbosity(cls):
        return 0

    @classmethod
    def setup_tenant(cls, tenant):
        """Subclasses may add required tenant fields and should call super()."""
        tenant.auto_create_schema = True

    @classmethod
    def setup_domain(cls, domain):
        domain.is_primary = True

    @classmethod
    def _remove_owned_test_tenant(cls):
        """Remove only this concrete class's deterministic preserved fixture."""
        connection.set_schema_to_public()
        tenant_model = get_tenant_model()
        schema_name = cls.get_test_schema_name()
        existing = tenant_model.objects.filter(schema_name=schema_name).first()
        if existing is not None:
            existing.delete(force_drop=True)
        # An interrupted --keepdb run can leave a schema without its Client row.
        if schema_exists(schema_name):
            quoted_schema = connection.ops.quote_name(schema_name)
            with connection.cursor() as cursor:
                cursor.execute(f"DROP SCHEMA {quoted_schema} CASCADE")


class TenantTestCase(TenantTestCaseMixin, DjangoTenantTestCase):
    """Reusable isolated tenant case for normal PostgreSQL-backed API tests."""

    @classmethod
    def setUpClass(cls):
        # django-tenants' upstream implementation always INSERTs its fixed
        # `test` tenant. Reconcile this class's own fixture before doing so.
        connection.set_schema_to_public()
        call_command(
            "migrate_schemas", schema_name=get_public_schema_name(),
            interactive=False, verbosity=0,
        )
        cls._remove_owned_test_tenant()

        domain_name = cls.get_test_tenant_domain()
        if domain_name not in settings.ALLOWED_HOSTS:
            settings.ALLOWED_HOSTS.append(domain_name)

        cls.tenant = get_tenant_model()(schema_name=cls.get_test_schema_name())
        cls.setup_tenant(cls.tenant)
        # Enforce explicit test provisioning even if a legacy subclass did not
        # call super(). Production Client defaults remain unchanged.
        cls.tenant.auto_create_schema = True
        cls.tenant.save(verbosity=cls.get_verbosity())
        call_command(
            "migrate_schemas", schema_name=cls.tenant.schema_name,
            interactive=False, verbosity=0,
        )

        cls.domain = get_tenant_domain_model()(
            tenant=cls.tenant, domain=domain_name,
        )
        cls.setup_domain(cls.domain)
        cls.domain.save()
        connection.set_tenant(cls.tenant)

    @classmethod
    def tearDownClass(cls):
        try:
            connection.set_schema_to_public()
            cls._remove_owned_test_tenant()
        finally:
            domain_name = cls.get_test_tenant_domain()
            if domain_name in settings.ALLOWED_HOSTS:
                settings.ALLOWED_HOSTS.remove(domain_name)


class TenantTransactionTestCase(TenantTestCaseMixin, TransactionTestCase):
    """A committed-fixture tenant case suitable for multi-connection race tests."""

    tenant = None
    domain = None

    @classmethod
    def setup_tenant(cls, tenant):
        pass

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        call_command(
            "migrate_schemas", schema_name=get_public_schema_name(),
            interactive=False, verbosity=0,
        )
        cls._remove_owned_test_tenant()
        # Module names commonly contain underscores, which are invalid in HTTP
        # hostnames and cause TenantMainMiddleware to return 404 before routing.
        domain_name = cls.get_test_tenant_domain()
        if domain_name not in settings.ALLOWED_HOSTS:
            settings.ALLOWED_HOSTS.append(domain_name)
        cls._test_domain_name = domain_name
        schema_name = cls.get_test_schema_name()
        cls.tenant = get_tenant_model()(schema_name=schema_name)
        cls.setup_tenant(cls.tenant)
        # Production tenants are provisioned explicitly, so Client defaults this
        # to False. Concurrency tests need a complete tenant schema of their own.
        cls.tenant.auto_create_schema = True
        cls.tenant.save(verbosity=0)
        # With --keepdb an orphaned/incomplete test schema can predate the tenant
        # row. Always reconcile its tenant migration state before test fixtures.
        call_command(
            "migrate_schemas", schema_name=cls.tenant.schema_name,
            interactive=False, verbosity=0,
        )
        cls.domain = get_tenant_domain_model().objects.create(
            tenant=cls.tenant, domain=domain_name,
        )
        connection.set_tenant(cls.tenant)

    @classmethod
    def tearDownClass(cls):
        connection.set_schema_to_public()
        cls.domain.delete()
        cls.tenant.delete(force_drop=True)
        if cls._test_domain_name in settings.ALLOWED_HOSTS:
            settings.ALLOWED_HOSTS.remove(cls._test_domain_name)
        super().tearDownClass()
