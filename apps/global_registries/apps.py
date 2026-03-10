from django.apps import AppConfig


class GlobalRegistriesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.global_registries"
    verbose_name = "Global Registries (countries, calendars, grade scales)"
