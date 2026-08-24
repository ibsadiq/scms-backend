from django.db import connection
from rest_framework_simplejwt.tokens import RefreshToken


TENANT_CLAIM = "tenant_slug"


def current_tenant_schema():
    """Return the resolved database schema used for the current request."""
    return connection.schema_name or "public"


def tenant_refresh_token_for_user(user):
    """Issue a refresh token bound to the currently resolved tenant schema."""
    token = RefreshToken.for_user(user)
    token[TENANT_CLAIM] = current_tenant_schema()
    return token
