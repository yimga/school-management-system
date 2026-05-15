from django.apps import AppConfig


class MigrationCloudConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.migration_cloud"
    verbose_name = "Migration Cloud"
