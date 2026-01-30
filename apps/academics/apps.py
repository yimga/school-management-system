from django.apps import AppConfig


class AcademicsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.academics"
    verbose_name = "🎓 Academic Structure"

    def ready(self):
        import apps.academics.signals  # noqa: F401
