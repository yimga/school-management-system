"""
Canonical SKU contracts for marketplace monetization closure.

Every monetizable surface maps to one row here (intentional coverage); not every SKU
must bill today. Meter codes align with apps.billing.UsageMeter.metric_code where used.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BillingModel(str, Enum):
    FREE = "free"
    SUBSCRIPTION = "subscription"
    USAGE = "usage"
    ONE_TIME = "one_time"
    REVENUE_SHARE = "revenue_share"


class SettlementDependency(str, Enum):
    INTERNAL = "internal"
    EXTERNAL_PSP = "external_psp"
    MANUAL = "manual"


@dataclass(frozen=True)
class MarketplaceSkuContract:
    sku_key: str
    display_name: str
    billing_model: BillingModel
    unit_name: str
    unit_price_hint: str
    meter_event_name: str
    entitlement_required: bool
    platform_fee_percent: str | None
    settlement_dependency: SettlementDependency
    active: bool


# Unified catalog (closure proof: enumerate intent for each monetizable category).
MARKETPLACE_SKU_CONTRACTS: tuple[MarketplaceSkuContract, ...] = (
    MarketplaceSkuContract(
        sku_key="mkt_app_subscription",
        display_name="Marketplace app subscription",
        billing_model=BillingModel.SUBSCRIPTION,
        unit_name="seat_or_school_month",
        unit_price_hint="MarketplaceApp.price + billing_interval",
        meter_event_name="",
        entitlement_required=True,
        platform_fee_percent="MARKETPLACE_PLATFORM_FEE_PERCENT",
        settlement_dependency=SettlementDependency.EXTERNAL_PSP,
        active=True,
    ),
    MarketplaceSkuContract(
        sku_key="mkt_app_usage",
        display_name="Marketplace app usage (metered)",
        billing_model=BillingModel.USAGE,
        unit_name="usage_unit",
        unit_price_hint="MarketplaceApp.price as floor / overage table",
        meter_event_name="marketplace_app_usage",
        entitlement_required=True,
        platform_fee_percent="MARKETPLACE_PLATFORM_FEE_PERCENT",
        settlement_dependency=SettlementDependency.EXTERNAL_PSP,
        active=True,
    ),
    MarketplaceSkuContract(
        sku_key="platform_ai_usage",
        display_name="AI usage (platform meter)",
        billing_model=BillingModel.USAGE,
        unit_name="ai_unit",
        unit_price_hint="site AI metering policy",
        meter_event_name="ai_usage_units",
        entitlement_required=False,
        platform_fee_percent=None,
        settlement_dependency=SettlementDependency.EXTERNAL_PSP,
        active=True,
    ),
    MarketplaceSkuContract(
        sku_key="platform_sms_messaging",
        display_name="SMS / messaging segments",
        billing_model=BillingModel.USAGE,
        unit_name="segment",
        unit_price_hint="carrier table",
        meter_event_name="sms_segments",
        entitlement_required=False,
        platform_fee_percent=None,
        settlement_dependency=SettlementDependency.EXTERNAL_PSP,
        active=True,
    ),
    MarketplaceSkuContract(
        sku_key="platform_payment_fees",
        display_name="Payments / transaction fees",
        billing_model=BillingModel.USAGE,
        unit_name="rail_event",
        unit_price_hint="regional payment profile",
        meter_event_name="payment_rail_events",
        entitlement_required=False,
        platform_fee_percent=None,
        settlement_dependency=SettlementDependency.MANUAL,
        active=True,
    ),
    MarketplaceSkuContract(
        sku_key="premium_report_export",
        display_name="Premium report / export generation",
        billing_model=BillingModel.USAGE,
        unit_name="run",
        unit_price_hint="governed export pricing",
        meter_event_name="report_generation_runs",
        entitlement_required=False,
        platform_fee_percent=None,
        settlement_dependency=SettlementDependency.INTERNAL,
        active=True,
    ),
    MarketplaceSkuContract(
        sku_key="automation_workflow_monetized",
        display_name="Automation / workflow (monetized tier)",
        billing_model=BillingModel.USAGE,
        unit_name="workflow_run",
        unit_price_hint="plan-gated",
        meter_event_name="workflow_metered_run",
        entitlement_required=True,
        platform_fee_percent=None,
        settlement_dependency=SettlementDependency.INTERNAL,
        active=True,
    ),
    MarketplaceSkuContract(
        sku_key="developer_api_usage",
        display_name="Developer API usage (monetized)",
        billing_model=BillingModel.USAGE,
        unit_name="api_call",
        unit_price_hint="apicenter plan",
        meter_event_name="developer_api_call",
        entitlement_required=False,
        platform_fee_percent=None,
        settlement_dependency=SettlementDependency.EXTERNAL_PSP,
        active=True,
    ),
)


def all_sku_keys() -> frozenset[str]:
    return frozenset(c.sku_key for c in MARKETPLACE_SKU_CONTRACTS)


def get_contract(sku_key: str) -> MarketplaceSkuContract | None:
    for c in MARKETPLACE_SKU_CONTRACTS:
        if c.sku_key == sku_key:
            return c
    return None
