from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from .tokens import TENANT_CLAIM, current_tenant_schema


class TenantBoundJWTAuthentication(JWTAuthentication):
    """Reject JWTs that were not issued for the resolved tenant schema."""

    def get_user(self, validated_token):
        token_schema = validated_token.get(TENANT_CLAIM)
        current_schema = current_tenant_schema()

        if not token_schema:
            raise AuthenticationFailed(
                "Token is not bound to a tenant. Please sign in again.",
                code="token_not_tenant_bound",
            )
        if token_schema != current_schema:
            raise AuthenticationFailed(
                "Token tenant does not match the requested tenant.",
                code="token_tenant_mismatch",
            )

        return super().get_user(validated_token)
