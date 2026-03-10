"""
Integrations marketplace bounded-context surface.

These re-exports provide the domain import path now so service and UI code can
stop depending on legacy marketplace module paths during the cutover.
"""

from apps.marketplace.models import (
    AppAuditLog,
    AppBillingLedger,
    AppInstallation,
    AppScope,
    AppVersionCompat,
    CapabilityRegistry,
    MarketplaceApp,
    MarketplaceListing,
    MarketplaceReview,
    PublisherOrganization,
    ScopeGrant,
)

__all__ = [
    "AppAuditLog",
    "AppBillingLedger",
    "AppInstallation",
    "AppScope",
    "AppVersionCompat",
    "CapabilityRegistry",
    "MarketplaceApp",
    "MarketplaceListing",
    "MarketplaceReview",
    "PublisherOrganization",
    "ScopeGrant",
]
