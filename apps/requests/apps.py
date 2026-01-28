from django.apps import AppConfig


class RequestsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.requests"
    verbose_name = "Access Requests"

    def ready(self):
        # Register signals lazily to avoid circular imports.
        from . import signals  # noqa: F401
