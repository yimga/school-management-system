from django.apps import AppConfig


class SchoolOpsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.schoolops"
    verbose_name = "School Operations"

    def ready(self) -> None:  # noqa: D401
        """Register signal handlers (v3.32.0 — low-balance notification)."""
        # Imported for side-effect: registers post_save / pre_save handlers
        # on :class:`apps.schoolops.models.MealPlanBalance`.
        from apps.schoolops import signals  # noqa: F401
