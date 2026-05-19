from django.apps import AppConfig


class MigrationCloudConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.migration_cloud"
    verbose_name = "Migration Cloud"

    def ready(self) -> None:  # pragma: no cover — boot wiring
        # v3.40.0 Agent 7 — customer-facing intake signal handlers.
        # Import is best-effort: a broken import here would block app
        # loading entirely. The handlers themselves are dispatched
        # directly from the customer view layer so this hook is
        # currently a passive registration.
        try:
            from . import signals_intake
            signals_intake.register_signal_handlers()
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "migration_cloud.apps: signals_intake import failed"
            )
        # v3.40.0 Agent 13 — smoke-result archival (Celery task_postrun
        # signal). Idempotent under double-import; a failure here MUST
        # NOT block app loading nor mask the signals_intake wire above.
        try:
            from . import tasks_smoke_archival
            tasks_smoke_archival.register_smoke_archival_signal()
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "migration_cloud.apps: tasks_smoke_archival wire failed"
            )
