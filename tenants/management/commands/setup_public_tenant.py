import os
from django.core.management.base import BaseCommand
from django.db import connection
from django_tenants.utils import schema_context
from tenants.models import Client, Domain, TenantStatus

class Command(BaseCommand):
    help = 'Automatically sets up the public schema and domain from .env'

    def handle(self, *args, **options):
        # Pull from environment variables
        schema_name = os.getenv('PUBLIC_SCHEMA_NAME', 'public')
        domain_name = os.getenv('PUBLIC_DOMAIN', 'localhost')
        platform_name = os.getenv('PLATFORM_NAME', 'SSync')

        self.stdout.write(f"Attempting to setup public tenant: {domain_name}...")

        # 1. Create the Client (Tenant) if it doesn't exist
        tenant, created = Client.objects.get_or_create(
            schema_name=schema_name,
            defaults={'name': platform_name, 'status': TenantStatus.ACTIVE}
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f"Created tenant: {schema_name}"))
        else:
            self.stdout.write(f"Tenant {schema_name} already exists.")

        # 2. Create the Domain if it doesn't exist
        domain, domain_created = Domain.objects.get_or_create(
            domain=domain_name,
            defaults={'tenant': tenant, 'is_primary': True}
        )

        if domain_created:
            self.stdout.write(self.style.SUCCESS(f"Created domain: {domain_name}"))
        else:
            self.stdout.write(f"Domain {domain_name} already exists.")

        self.stdout.write(self.style.SUCCESS("✅ Public schema automation complete"))