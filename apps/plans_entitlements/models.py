"""
Plans and entitlements bounded-context ownership surface.

These proxy-owner models let billing and entitlement code target the new domain
app now while keeping the current tables intact.
"""

from apps.billing.models import (
    BillingAccount as LegacyBillingAccount,
    BillingProcessorSyncEvent as LegacyBillingProcessorSyncEvent,
    PlatformLedgerEntry as LegacyPlatformLedgerEntry,
    Quote as LegacyQuote,
    RevenueSharePayout as LegacyRevenueSharePayout,
    TenantSubscription as LegacyTenantSubscription,
    UsageMeter as LegacyUsageMeter,
)
from apps.siteconfig.models_platform_catalog import (
    CountryMultiplier as LegacyCountryMultiplier,
    Plan as LegacyPlan,
    PlanAddon as LegacyPlanAddon,
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


BillingAccount = _proxy_model(
    LegacyBillingAccount,
    app_label="plans_entitlements",
    doc="Plans & Entitlements owner surface for billing accounts.",
)
BillingProcessorSyncEvent = _proxy_model(
    LegacyBillingProcessorSyncEvent,
    app_label="plans_entitlements",
    doc="Plans & Entitlements owner surface for processor sync events.",
)
CountryMultiplier = _proxy_model(
    LegacyCountryMultiplier,
    app_label="plans_entitlements",
    doc="Plans & Entitlements owner surface for regional price multipliers.",
)
PlatformLedgerEntry = _proxy_model(
    LegacyPlatformLedgerEntry,
    app_label="plans_entitlements",
    doc="Plans & Entitlements owner surface for platform commercial ledger events.",
)
Plan = _proxy_model(
    LegacyPlan,
    app_label="plans_entitlements",
    doc="Plans & Entitlements owner surface for plan definitions.",
)
PlanAddon = _proxy_model(
    LegacyPlanAddon,
    app_label="plans_entitlements",
    doc="Plans & Entitlements owner surface for add-on definitions.",
)
Quote = _proxy_model(
    LegacyQuote,
    app_label="plans_entitlements",
    doc="Plans & Entitlements owner surface for commercial quote state.",
)
RevenueSharePayout = _proxy_model(
    LegacyRevenueSharePayout,
    app_label="plans_entitlements",
    doc="Plans & Entitlements owner surface for revenue-share payouts.",
)
TenantSubscription = _proxy_model(
    LegacyTenantSubscription,
    app_label="plans_entitlements",
    doc="Plans & Entitlements owner surface for tenant subscription state.",
)
UsageMeter = _proxy_model(
    LegacyUsageMeter,
    app_label="plans_entitlements",
    doc="Plans & Entitlements owner surface for usage metering.",
)

__all__ = [
    "BillingAccount",
    "BillingProcessorSyncEvent",
    "CountryMultiplier",
    "PlatformLedgerEntry",
    "Plan",
    "PlanAddon",
    "Quote",
    "RevenueSharePayout",
    "TenantSubscription",
    "UsageMeter",
]
