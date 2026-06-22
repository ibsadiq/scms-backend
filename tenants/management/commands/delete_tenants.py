from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from tenants.models import Client, Domain


class Command(BaseCommand):
    help = 'Delete tenant(s) including Client, Domain, and Database Schema'

    def add_arguments(self, parser):
        parser.add_argument(
            '--subdomain',
            type=str,
            help='Subdomain of tenant to delete (e.g., greenvalley)',
        )
        parser.add_argument(
            '--schema',
            type=str,
            help='Schema name of tenant to delete (e.g., greenvalley_school)',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Delete ALL tenants (except public and localhost)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompt',
        )

    def handle(self, *args, **options):
        subdomain = options.get('subdomain')
        schema = options.get('schema')
        delete_all = options.get('all')
        force = options.get('force')

        if not (subdomain or schema or delete_all):
            raise CommandError('Must specify --subdomain, --schema, or --all')

        # Get tenants to delete
        if delete_all:
            tenants = Client.objects.exclude(schema_name='public')
        elif subdomain:
            # Find by domain
            try:
                domain = Domain.objects.get(domain__icontains=subdomain)
                tenants = [domain.tenant]
            except Domain.DoesNotExist:
                raise CommandError(f'No tenant found with subdomain: {subdomain}')
        elif schema:
            try:
                tenants = [Client.objects.get(schema_name=schema)]
            except Client.DoesNotExist:
                raise CommandError(f'No tenant found with schema: {schema}')

        # Safety check: Never delete public or localhost
        protected_schemas = ['public']
        protected_domains = ['localhost', '127.0.0.1', 'localhost:8000']
        
        safe_tenants = []
        for tenant in tenants:
            # Check if schema is protected
            if tenant.schema_name in protected_schemas:
                self.stdout.write(
                    self.style.WARNING(f'⚠️  Skipping protected schema: {tenant.schema_name}')
                )
                continue
            
            # Check if any domain is protected
            domains = tenant.domains.all()
            if any(d.domain in protected_domains for d in domains):
                self.stdout.write(
                    self.style.WARNING(f'⚠️  Skipping protected domain: {tenant.name}')
                )
                continue
            
            safe_tenants.append(tenant)

        if not safe_tenants:
            self.stdout.write(self.style.WARNING('No tenants to delete'))
            return

        # Display what will be deleted
        self.stdout.write(self.style.WARNING(f'\n🗑️  Will delete {len(safe_tenants)} tenant(s):\n'))
        for tenant in safe_tenants:
            domains = ', '.join([d.domain for d in tenant.domains.all()])
            self.stdout.write(f'  • {tenant.name}')
            self.stdout.write(f'    Schema: {tenant.schema_name}')
            self.stdout.write(f'    Domains: {domains}')
            self.stdout.write('')

        # Confirm deletion
        if not force:
            confirm = input('\n⚠️  Are you sure? This CANNOT be undone! (yes/no): ')
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.WARNING('❌ Aborted'))
                return

        # Delete tenants
        deleted_count = 0
        for tenant in safe_tenants:
            try:
                with transaction.atomic():
                    schema_name = tenant.schema_name
                    tenant_name = tenant.name
                    
                    # Delete Client (this cascades to Domains)
                    tenant.delete()
                    
                    # Drop database schema
                    with connection.cursor() as cursor:
                        cursor.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
                    
                    deleted_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'✅ Deleted: {tenant_name} ({schema_name})')
                    )
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Error deleting {tenant.name}: {e}')
                )

        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(f'✅ Successfully deleted {deleted_count} tenant(s)')
        )