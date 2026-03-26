"""Django app config so dashboard templatetags and tests resolve under INSTALLED_APPS."""

from django.apps import AppConfig


class DashboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.dashboard"
    label = "rms_dashboard"
    verbose_name = "Dashboard (decision surfaces)"
