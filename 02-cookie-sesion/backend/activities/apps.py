from django.apps import AppConfig


class ActivitiesConfig(AppConfig):
    """Registra el dominio de esta carpeta sin configurar otros mecanismos."""
    default_auto_field = "django.db.models.BigAutoField"
    name = "activities"
