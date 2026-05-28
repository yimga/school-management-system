from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.api"
    label = "api"
    verbose_name = "API"

    def ready(self) -> None:  # noqa: D401 — Django hook
        # v4.00.0: wire edge-cache purge signals.
        try:
            from services.edge_cache_signals import register_all

            register_all()
        except ImportError:
            pass
