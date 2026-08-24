from school.testcases import TenantTestCase

from tenants.models import TenantStatus


class JobsTenantTestCase(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        tenant.name = f"{cls.__name__} School"
        tenant.status = TenantStatus.ACTIVE
