from django.apps import AppConfig


class IntegrationsMarketplaceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integrations_marketplace"
    verbose_name = (
        "Integrations & Marketplace (providers, connectors, install metadata)"
    )
