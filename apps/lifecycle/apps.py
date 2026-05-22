from django.apps import AppConfig


class LifecycleConfig(AppConfig):
    name = "apps.lifecycle"
    label = "lifecycle"
    verbose_name = "School Lifecycle"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Side-effect-free signal registration; safe at import time.
        from . import signals  # noqa: F401
