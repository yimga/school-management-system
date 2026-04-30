from django.apps import AppConfig


class SyncEngineConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sync_engine"
    label = "sync_engine"
    verbose_name = "Offline sync engine"
