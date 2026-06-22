"""
Tenant Header Resolution Middleware
Reads X-Tenant-Slug header and activates the appropriate tenant schema.
Falls back to subdomain-based routing from django-tenants.
"""
from django.http import JsonResponse
from django.db import connection
from django_tenants.utils import tenant_context
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class TenantHeaderMiddleware:
    """
    Middleware to resolve tenant from X-Tenant-Slug header.
    
    Precedence:
    1. X-Tenant-Slug header (used by frontend/API clients)
    2. django-tenants subdomain routing (Host header)
    3. Fallback to public schema for main domain
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Extract tenant slug from header
        tenant_slug = request.headers.get('X-Tenant-Slug', '').strip()

        # If no header, try to resolve from subdomain (django-tenants default behavior)
        # This happens before this middleware, so connection.schema_name is already set
        if not tenant_slug:
            # Already handled by TenantMainMiddleware
            return self.get_response(request)

        # If header slug refers to the public schema we allow it directly
        from django.conf import settings
        public_slug = getattr(settings, 'PUBLIC_TENANT_SLUG', None) or getattr(settings, 'BASE_DOMAIN', 'public')
        if tenant_slug == public_slug or tenant_slug == 'public':
            # keep default connection.schema_name (public)
            request.tenant_slug = tenant_slug
            return self.get_response(request)

        # Validate and switch to the specified tenant
        if not self._validate_and_set_tenant(request, tenant_slug):
            return JsonResponse({
                'error': 'Invalid Tenant',
                'detail': f"Tenant '{tenant_slug}' not found or inaccessible.",
                'tenant_slug': tenant_slug,
            }, status=400)

        # Store tenant info in request for view-level access
        request.tenant_slug = tenant_slug

        response = self.get_response(request)
        return response

    def _validate_and_set_tenant(self, request, tenant_slug):
        """
        Validate tenant exists and activate its schema.
        
        Returns:
            bool: True if tenant activated successfully, False otherwise.
        """
        try:
            # Import here to avoid circular imports
            from tenants.models import Client

            # Find tenant by slug (which maps to schema_name in django-tenants)
            tenant = Client.objects.get(schema_name=tenant_slug)

            # Check if tenant is active
            if not tenant.is_active:
                logger.warning(f"Access attempted to inactive tenant: {tenant_slug} (status: {tenant.status})")
                return False

            # Activate the tenant's schema
            connection.set_tenant(tenant)
            logger.debug(f"Tenant schema activated: {tenant_slug}")
            return True

        except Client.DoesNotExist:
            # schema_name lookup failed — try resolving via the Domain model.
            # This handles the case where the subdomain differs from schema_name,
            # e.g. subdomain 'abchigh' → domain 'abchigh.localhost' → schema 'abc_high'.
            from tenants.models import Domain
            base_domain = getattr(settings, 'BASE_DOMAIN', 'localhost').split(':')[0]
            try:
                domain_obj = Domain.objects.select_related('tenant').get(
                    domain=f'{tenant_slug}.{base_domain}'
                )
                tenant = domain_obj.tenant
                if not tenant.is_active:
                    logger.warning(f"Access attempted to inactive tenant via domain: {tenant_slug}")
                    return False
                connection.set_tenant(tenant)
                logger.debug(f"Tenant schema activated via domain lookup: {tenant_slug} → {tenant.schema_name}")
                return True
            except Domain.DoesNotExist:
                logger.warning(f"Tenant not found: {tenant_slug}")
                return False
        except Exception as e:
            logger.error(f"Error validating tenant {tenant_slug}: {str(e)}")
            return False
