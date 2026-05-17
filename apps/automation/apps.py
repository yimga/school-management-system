from django.apps import AppConfig


class AutomationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.automation"
    verbose_name = "Automation"

    def ready(self):
        try:
            from apps.automation.domain_event_bridge import (
                register_domain_event_trigger_subscriber,
            )

            register_domain_event_trigger_subscriber()
        except Exception:
            import logging

            logging.getLogger(__name__).debug(
                "domain_event_trigger_subscriber registration skipped", exc_info=True
            )
