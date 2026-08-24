from django.db import connection

from administration.models import School
from tenants.models import Client


class BrandingResolver:
    """Use tenant Client branding first; fill missing legacy values from the active School."""

    @classmethod
    def resolve(cls):
        tenant = getattr(connection, "tenant", None)
        if not isinstance(tenant, Client):
            tenant = None
        school = School.objects.filter(active=True).first() or School.objects.first()

        def first(*values):
            return next((value for value in values if value not in (None, "")), "")

        tenant_logo = tenant.get_logo_url() if tenant and tenant.logo else ""
        school_logo = school.school_logo.url if school and school.school_logo else ""
        return {
            "name": first(getattr(tenant, "name", None), getattr(school, "name", None)),
            "logo": first(tenant_logo, school_logo),
            "motto": first(getattr(tenant, "motto", None)),
            "address": first(getattr(tenant, "address", None), getattr(school, "address", None)),
            "phone": first(getattr(tenant, "contact_phone", None), getattr(school, "telephone", None)),
            "email": first(getattr(tenant, "contact_email", None), getattr(school, "school_email", None)),
        }
