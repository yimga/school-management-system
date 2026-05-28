from django.apps import AppConfig


class WalStreamConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.wal_stream"
    label = "wal_stream"
    verbose_name = "WAL Stream (v4)"
