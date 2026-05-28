from django.apps import AppConfig


class AcademicsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.academics"
    verbose_name = "🎓 Academic Structure"

    def ready(self):
        import apps.academics.signals  # noqa: F401
        # v4.00.13: wire adaptive kernel post-save signal on Evaluation rows.
        try:
            from apps.academics.signals_adaptive import connect_adaptive_signals
            connect_adaptive_signals()
        except Exception:  # noqa: BLE001 — never block app boot
            pass
