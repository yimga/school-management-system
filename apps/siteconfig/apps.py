from django.apps import AppConfig
from django.contrib import admin


class SiteconfigConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = 'apps.siteconfig'
    verbose_name = '⚙️ System Configuration'
    
    def ready(self):
        admin.site.login_template = "auth/login.html"
