from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = 'users'

    def ready(self):
        # Register drf-spectacular extensions without coupling authentication
        # behavior to schema generation.
        from . import schema  # noqa: F401
