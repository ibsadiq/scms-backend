from django.contrib.sites.models import Site
from django.http import JsonResponse
from django.urls import resolve

class TenantMiddleware:
    """
    Middleware to detect tenant from subdomain and enforce onboarding.

    - Detects tenant from the request's host/domain
    - Attaches tenant to request object
    - Redirects to onboarding if tenant exists but onboarding is not completed
    - Allows access to onboarding endpoints and admin without restriction
    """

    # Paths that should bypass onboarding check
    ALLOWED_PATHS = [
        '/api/tenants/onboarding/',
        '/api/tenants/debug/',
        '/api/schema/',
        '/admin/',
        '/static/',
        '/media/',
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(":")[0]

        try:
            site = Site.objects.get(domain=host)
            request.site = site
            request.tenant = site.tenant
        except Site.DoesNotExist:
            request.site = None
            request.tenant = None

        # Check if onboarding is required
        if request.tenant and not request.tenant.onboarding_completed:
            # Check if the current path is allowed
            if not self._is_allowed_path(request.path):
                return JsonResponse({
                    "error": "Onboarding required",
                    "message": "This tenant has not completed onboarding. Please complete the setup process.",
                    "onboarding_required": True,
                    "redirect_to": "/api/tenants/onboarding/check/"
                }, status=403)

        return self.get_response(request)

    def _is_allowed_path(self, path):
        """Check if the path is allowed to bypass onboarding"""
        for allowed_path in self.ALLOWED_PATHS:
            if path.startswith(allowed_path):
                return True
        return False
