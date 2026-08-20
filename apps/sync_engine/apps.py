from django.apps import AppConfig


class SyncEngineConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sync_engine"
    label = "sync_engine"
    verbose_name = "Offline sync engine"

    def ready(self) -> None:  # noqa: D401 - Django hook
        # Deletion propagation. A deleted row leaves nothing for the delta scan to find,
        # so without a post_delete receiver a deletion is the one change that can never
        # cross the sync boundary. register_delete_signals() never raises: it is better
        # for deletions not to propagate than for a signal-wiring failure to take down
        # every deployment at import time.
        from apps.sync_engine.tombstones import register_delete_signals

        register_delete_signals()

        # The long-poll changes feed answers "is there anything new?" from an in-memory
        # beacon rather than fifteen existence queries a second. Also never raises.
        from apps.sync_engine.change_beacon import register_change_signals

        register_change_signals()
