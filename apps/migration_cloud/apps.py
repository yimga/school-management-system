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
        # Register the weekly audit-chain verifier so the
        # ``accounts-verify-audit-chain`` beat entry resolves to a real task
        # (this app has no autodiscovered tasks.py; importing the module here
        # registers its @shared_task at app-ready). The task is a READ-ONLY
        # verifier — it wraps ``verify_audit_chain --all-tenants`` and only
        # logs/alerts on a detected break — so scheduling it has no destructive
        # or outbound side effects beyond a tamper alert.
        try:
            from . import tasks_audit  # noqa: F401 — import registers the @shared_task
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "migration_cloud.apps: tasks_audit import failed"
            )
        # Register the Migration Cloud Celery tasks (advance / apply / fetch_assets).
        # This app has NO autodiscovered ``tasks.py``, so without this import
        # ``fetch_assets_task`` is unregistered and a broker-backed worker silently
        # drops asset fetches — ``.delay()`` succeeds on the producer but the worker
        # has no such task. (The critical advance→apply path runs via the durable
        # HeavyWorkOutbox drain calling the pipeline directly, so it does not depend
        # on these registrations; the media-asset side branch does.)
        try:
            from . import celery_tasks  # noqa: F401 — import registers the @shared_task set
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "migration_cloud.apps: celery_tasks import failed"
            )
        # Register the four beat-scheduled Migration Cloud tasks whose
        # @shared_task lives outside an autodiscovered tasks.py, so their beat
        # entries resolve instead of silently never running. All four are safe
        # to schedule:
        #   * tasks_retention.purge_completed_migration_bundles_audit_task —
        #     DRY-RUN audit, never mutates (only counts + info alerts).
        #   * tasks_smoke.run_smoke_against_synthetic_tenant — kill-switched OFF
        #     by default (MIGRATION_CLOUD_SMOKE_NIGHTLY_ENABLED); no-op in prod.
        #   * tasks_alerts.token_rotation_watchdog — read-only scan + warning
        #     alerts; never mutates.
        #   * api.webhook_dispatch.deliver_due_task — outbound, but self-gated
        #     OFF by default (MIGRATION_CLOUD_WEBHOOK_DISPATCH_ENABLED).
        for _beat_module in (
            "tasks_retention",
            "tasks_smoke",
            "tasks_alerts",
        ):
            try:
                __import__(f"apps.migration_cloud.{_beat_module}")
            except Exception:  # noqa: BLE001
                import logging
                logging.getLogger(__name__).exception(
                    "migration_cloud.apps: %s import failed", _beat_module
                )
        try:
            from .api import webhook_dispatch  # noqa: F401 — registers deliver_due_task
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "migration_cloud.apps: webhook_dispatch import failed"
            )
