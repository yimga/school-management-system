from django.apps import AppConfig
from django.contrib import admin


class SiteconfigConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.siteconfig"

    def ready(self):
        admin.site.login_template = "auth/login.html"
