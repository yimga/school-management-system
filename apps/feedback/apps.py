from django.apps import AppConfig


class FeedbackConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.feedback"
    verbose_name = "Voice of Customer"

    def ready(self):
        # Move 4 — wire post_save signal handlers for help-center loop closure.
        from apps.feedback import signals  # noqa: F401
