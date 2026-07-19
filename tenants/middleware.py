"""
Tenant Access Control Middleware
Blocks suspended tenants from accessing the API.
"""
from django.http import JsonResponse
from django.db import connection
import logging

logger = logging.getLogger(__name__)


class TenantAccessMiddleware:
    """
    Middleware to check if tenant is active.
    Blocks API access for suspended schools.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Skip check for public schema
        if connection.schema_name == 'public':
            return self.get_response(request)
        
        # Get current tenant
        tenant = connection.tenant
        
        # Check if tenant is active
        if not tenant.is_active:
            return JsonResponse({
                'error': 'School Suspended',
                'detail': f'Access to {tenant.name} has been suspended. Please contact support.',
                'school_name': tenant.name,
                'schema_name': tenant.schema_name,
                'contact_email': 'support@tarklish.tech',
                'support_url': 'https://ssyportal.com/#contact'
            }, status=403)
        
        # Tenant is active, proceed normally
        response = self.get_response(request)
        return response
    

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
        tenant_slug = request.headers.get('X-Tenant-Slug', '').strip().lower()
        if tenant_slug in ('www', ''):
            tenant_slug = None  # public schema

        # If no header, try to resolve from subdomain (django-tenants default behavior)
        # This happens before this middleware, so connection.schema_name is already set
        if not tenant_slug:
            # Already handled by TenantMainMiddleware
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
        try:
            from tenants.models import Client, Domain
            from django.conf import settings


            # Resolve via Domain table instead of assuming schema_name matches the slug
            base_domain = getattr(settings, 'BASE_DOMAIN', 'ssyncportal.com')
            domain_lookup = f"{tenant_slug}.{base_domain}"
            domain_obj = Domain.objects.select_related('tenant').get(domain=domain_lookup)
            tenant = domain_obj.tenant

            if not tenant.is_active:
                logger.warning(f"Access attempted to inactive tenant: {tenant.schema_name} (status: {tenant.status})")
                return False

            connection.set_tenant(tenant)
            logger.debug(f"Tenant schema activated: {tenant.schema_name}")
            return True

        except Domain.DoesNotExist:
            logger.warning(f"Tenant not found for slug: {tenant_slug}")
            return False
        except Exception as e:
            logger.error(f"Error validating tenant {tenant_slug}: {str(e)}")
            return False