from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.analytics"
    verbose_name = "📈 Analytics & Insights"

    def ready(self):
        from apps.analytics import ews_signals  # noqa: F401
