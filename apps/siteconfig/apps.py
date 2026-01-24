from django.apps import AppConfig
from django.contrib import admin


class SiteconfigConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = 'apps.siteconfig'
    verbose_name = '⚙️ System Configuration'
    
    def ready(self):
        # Ensure additional dashboard models are imported so Django can detect them for migrations
        try:
            from . import models_dashboard  # noqa: F401
        except Exception:
            pass
        admin.site.login_template = "auth/login.html"
