from django.apps import AppConfig


class AthleticsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.athletics"
    verbose_name = "Athletics"

    def ready(self) -> None:
        # Import signal handlers if/when present; guarded so a missing module
        # never breaks app loading during incremental build-out.
        try:
            from . import signals  # noqa: F401
        except ImportError:
            pass
