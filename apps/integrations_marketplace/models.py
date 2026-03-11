"""
Integrations marketplace bounded-context ownership surface.

These proxy-owner models consolidate provider/integration and app ecosystem
imports behind the north-star domain app while preserving current tables.
"""

from apps.marketplace.models import (
    AppAuditLog as LegacyAppAuditLog,
    AppBillingLedger as LegacyAppBillingLedger,
    AppInstallation as LegacyAppInstallation,
    AppScope as LegacyAppScope,
    AppVersionCompat as LegacyAppVersionCompat,
    CapabilityRegistry as LegacyCapabilityRegistry,
    MarketplaceApp as LegacyMarketplaceApp,
    MarketplaceListing as LegacyMarketplaceListing,
    MarketplaceReview as LegacyMarketplaceReview,
    PublisherOrganization as LegacyPublisherOrganization,
    ScopeGrant as LegacyScopeGrant,
)
from apps.siteconfig.models import (
    Integration as LegacyIntegration,
    ServiceIntegration as LegacyServiceIntegration,
)


def _proxy_model(legacy_model, *, app_label: str, doc: str):
    meta = type(
        "Meta",
        (),
        {
            "proxy": True,
            "app_label": app_label,
            "verbose_name": legacy_model._meta.verbose_name,
            "verbose_name_plural": legacy_model._meta.verbose_name_plural,
        },
    )
    return type(
        legacy_model.__name__,
        (legacy_model,),
        {
            "__module__": __name__,
            "__doc__": doc,
            "Meta": meta,
        },
    )


AppAuditLog = _proxy_model(
    LegacyAppAuditLog,
    app_label="integrations_marketplace",
    doc="Integrations & Marketplace owner surface for installation audit logs.",
)
AppBillingLedger = _proxy_model(
    LegacyAppBillingLedger,
    app_label="integrations_marketplace",
    doc="Integrations & Marketplace owner surface for marketplace billing ledger entries.",
)
AppInstallation = _proxy_model(
    LegacyAppInstallation,
    app_label="integrations_marketplace",
    doc="Integrations & Marketplace owner surface for tenant app installations.",
)
AppScope = _proxy_model(
    LegacyAppScope,
    app_label="integrations_marketplace",
    doc="Integrations & Marketplace owner surface for app scopes.",
)
AppVersionCompat = _proxy_model(
    LegacyAppVersionCompat,
    app_label="integrations_marketplace",
    doc="Integrations & Marketplace owner surface for app version compatibility rules.",
)
CapabilityRegistry = _proxy_model(
    LegacyCapabilityRegistry,
    app_label="integrations_marketplace",
    doc="Integrations & Marketplace owner surface for capability registry entries.",
)
Integration = _proxy_model(
    LegacyIntegration,
    app_label="integrations_marketplace",
    doc="Integrations & Marketplace owner surface for platform integrations.",
)
MarketplaceApp = _proxy_model(
    LegacyMarketplaceApp,
    app_label="integrations_marketplace",
    doc="Integrations & Marketplace owner surface for marketplace apps.",
)
MarketplaceListing = _proxy_model(
    LegacyMarketplaceListing,
    app_label="integrations_marketplace",
    doc="Integrations & Marketplace owner surface for marketplace listings.",
)
MarketplaceReview = _proxy_model(
    LegacyMarketplaceReview,
    app_label="integrations_marketplace",
    doc="Integrations & Marketplace owner surface for marketplace review workflows.",
)
PublisherOrganization = _proxy_model(
    LegacyPublisherOrganization,
    app_label="integrations_marketplace",
    doc="Integrations & Marketplace owner surface for publisher organizations.",
)
ScopeGrant = _proxy_model(
    LegacyScopeGrant,
    app_label="integrations_marketplace",
    doc="Integrations & Marketplace owner surface for scope grants.",
)
ServiceIntegration = _proxy_model(
    LegacyServiceIntegration,
    app_label="integrations_marketplace",
    doc="Integrations & Marketplace owner surface for service integrations.",
)

__all__ = [
    "AppAuditLog",
    "AppBillingLedger",
    "AppInstallation",
    "AppScope",
    "AppVersionCompat",
    "CapabilityRegistry",
    "Integration",
    "MarketplaceApp",
    "MarketplaceListing",
    "MarketplaceReview",
    "PublisherOrganization",
    "ScopeGrant",
    "ServiceIntegration",
]
