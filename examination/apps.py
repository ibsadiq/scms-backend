from django.apps import AppConfig


class ExaminationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'examination'

    def ready(self):
        """Import signals when app is ready"""
        import examination.signals
