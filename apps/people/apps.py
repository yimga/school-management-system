from django.apps import AppConfig


class PeopleConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = 'apps.people'
    verbose_name = '👥 People Management'
    
    def ready(self):
        """Import signal handlers when app is ready."""
        import apps.people.signals  # noqa
