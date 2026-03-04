from django.apps import AppConfig
from django.contrib import admin


class SiteconfigConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = 'apps.siteconfig'
    verbose_name = '⚙️ System Configuration'
    
    def ready(self):
        # Ensure additional dashboard and workflow models are imported for migrations
        try:
            from . import models_dashboard  # noqa: F401
        except Exception:
            pass
        try:
            from . import models_workflow  # noqa: F401
        except Exception:
            pass
        # Import signals for audit logging
        try:
            from . import signals  # noqa: F401
        except Exception:
            pass
        admin.site.login_template = "auth/login.html"
