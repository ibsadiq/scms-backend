from django.apps import AppConfig


class TenantsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tenants"
    verbose_name = "Tenants"
    verbose_name_plural = "Tenants"

    
    def ready(self):
        import tenants.signals 