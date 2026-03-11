from django.apps import AppConfig


class PlatformRuntimeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.platform_runtime"
    verbose_name = "Platform runtime (defaults, resolver)"
