from drf_spectacular.extensions import OpenApiAuthenticationExtension


class TenantBoundJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "users.authentication.TenantBoundJWTAuthentication"
    name = "tenantBearerAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "Tenant-bound JWT. Send the token in Authorization: Bearer <token>. "
                "The request host or X-Tenant-Slug must resolve to the token tenant."
            ),
        }
