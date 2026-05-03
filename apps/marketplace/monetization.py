"""
Marketplace monetization: catalog pricing hooks, tenant add-on subscriptions, platform fee splits,
usage metering helpers, and founder-facing aggregates (real DB rows only).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.marketplace.models import (
    MarketplaceApp,
    MarketplaceListing,
    PlatformMarketplaceEarning,
    TenantMarketplaceSubscription,
)


def get_platform_fee_percent() -> Decimal:
    raw = getattr(settings, "MARKETPLACE_PLATFORM_FEE_PERCENT", None)
    if raw is None:
        return Decimal("20")
    return Decimal(str(raw))


def _annual_to_monthly(amount: Decimal) -> Decimal:
    return (amount / Decimal("12")).quantize(Decimal("0.01"))


def assert_paid_install_billing_ready_or_raise(school, app: MarketplaceApp) -> None:
    """
    Hard gate for paid installs when MARKETPLACE_INSTALL_REQUIRES_PAID_BILLING is enabled.
    Requires processor-backed billing account (external customer ref).
    """
    if not getattr(settings, "MARKETPLACE_INSTALL_REQUIRES_PAID_BILLING", False):
        return
    charge = compute_install_charge(app)
    if charge <= 0:
        return
    from apps.billing.services import ensure_billing_account_for_school

    account, _ = ensure_billing_account_for_school(school)
    ref = (getattr(account, "external_customer_ref", None) or "").strip()
    if not ref:
        raise RuntimeError(
            "Paid marketplace install blocked: billing profile must include a processor "
            "customer (payment method on file) before installing this app."
        )


def compute_install_charge(app: MarketplaceApp) -> Decimal:
    """First-period charge surfaced to tenant ledger (subscription = list price; usage = 0 at install)."""
    if app.pricing_model == MarketplaceApp.PricingModel.FREE:
        return Decimal("0.00")
    price = Decimal(str(app.price or "0"))
    if app.pricing_model == MarketplaceApp.PricingModel.USAGE:
        return Decimal("0.00")
    if app.pricing_model == MarketplaceApp.PricingModel.SUBSCRIPTION:
        if app.billing_interval == MarketplaceApp.BillingInterval.ANNUAL:
            return price  # first invoice = annual list (simple contract)
        return price
    return Decimal("0.00")


def _split_gross(
    gross: Decimal,
    *,
    listing: MarketplaceListing | None,
) -> tuple[Decimal, Decimal, Decimal]:
    """Return (platform_fee, publisher_pool, publisher_share)."""
    fee_pct = get_platform_fee_percent()
    if gross <= 0:
        return Decimal("0.00"), Decimal("0.00"), Decimal("0.00")
    platform_fee = (gross * fee_pct / Decimal("100")).quantize(Decimal("0.01"))
    publisher_pool = (gross - platform_fee).quantize(Decimal("0.01"))
    rev_pct = Decimal("0")
    if listing is not None:
        rev_pct = Decimal(str(getattr(listing, "revenue_share_percent", None) or "0"))
    publisher_share = (publisher_pool * rev_pct / Decimal("100")).quantize(Decimal("0.01"))
    return platform_fee, publisher_pool, publisher_share


@transaction.atomic
def apply_marketplace_install_monetization(
    *,
    school,
    app: MarketplaceApp,
    installation,
    listing: MarketplaceListing | None = None,
) -> dict[str, Any]:
    """
    Ensure billing account, optional tenant add-on subscription row, ledger charge, earnings split.
    Idempotent: one PlatformLedgerEntry per installation reference ``app_install_{id}``; subscription upserted.
    """
    from apps.billing.models import PlatformLedgerEntry
    from apps.billing.services import ensure_billing_account_for_school, record_app_install_for_billing

    account, _ = ensure_billing_account_for_school(school)
    charge = compute_install_charge(app)
    ledger_ref = f"app_install_{getattr(installation, 'pk', '')}"
    already_charged = PlatformLedgerEntry.objects.filter(
        reference=ledger_ref,
        school=school,
        source="marketplace_app_install",
    ).exists()
    if not already_charged:
        record_app_install_for_billing(school, app, installation, amount=charge)

    lst = listing
    if lst is None:
        lst = getattr(app, "listing", None)

    sub, created = TenantMarketplaceSubscription.objects.get_or_create(
        installation=installation,
        defaults={
            "school": school,
            "app": app,
            "billing_account": account,
            "pricing_model": app.pricing_model,
            "unit_amount": Decimal(str(app.price or "0")),
            "billing_interval": app.billing_interval,
            "currency_code": getattr(account, "currency_code", None) or "USD",
            "status": TenantMarketplaceSubscription.Status.ACTIVE,
            "current_period_start": timezone.now(),
            "current_period_end": timezone.now() + timedelta(days=30),
            "metadata": {"source": "install_monetization"},
        },
    )
    if not created:
        sub.pricing_model = app.pricing_model
        sub.unit_amount = Decimal(str(app.price or "0"))
        sub.billing_interval = app.billing_interval
        sub.billing_account = account
        sub.save(
            update_fields=[
                "pricing_model",
                "unit_amount",
                "billing_interval",
                "billing_account",
                "updated_at",
            ]
        )

    curr = getattr(account, "currency_code", None) or "USD"
    snap = None
    try:
        from apps.marketplace.monetization_ledger_ops import (
            append_install_ledger_slice,
            classify_settlement_lane,
        )

        snap = classify_settlement_lane(school)
        append_install_ledger_slice(
            school=school,
            app=app,
            installation=installation,
            charge=charge,
            listing=lst,
            currency_code=curr,
            settlement_snapshot=snap,
        )
    except (ImportError, AttributeError, TypeError, ValueError):
        snap = None

    if charge > 0 and not already_charged:
        pf, pool, pub = _split_gross(charge, listing=lst)
        PlatformMarketplaceEarning.objects.create(
            school=school,
            app=app,
            installation=installation,
            listing=lst,
            source=PlatformMarketplaceEarning.Source.INSTALL,
            gross_amount=charge,
            platform_fee_amount=pf,
            publisher_pool_amount=pool,
            publisher_share_amount=pub,
            currency_code=curr,
            metadata={
                "platform_fee_percent": str(get_platform_fee_percent()),
                "revenue_share_percent": str(
                    getattr(lst, "revenue_share_percent", "") if lst else ""
                ),
            },
        )
        try:
            from apps.marketplace.monetization_ledger_ops import append_platform_fee_ledger

            append_platform_fee_ledger(
                school=school,
                app=app,
                installation=installation,
                gross=charge,
                platform_fee=pf,
                currency=curr,
                listing=lst,
            )
        except (ImportError, AttributeError, TypeError, ValueError):
            pass

    return {
        "charge": str(charge),
        "subscription_created": created,
        "platform_fee_percent": str(get_platform_fee_percent()),
    }


def cancel_marketplace_subscription_for_uninstall(installation) -> None:
    TenantMarketplaceSubscription.objects.filter(installation=installation).update(
        status=TenantMarketplaceSubscription.Status.CANCELED,
        canceled_at=timezone.now(),
    )


# Usage billing codes (monthly aggregation via UsageMeter)
USAGE_METRIC_SMS = "sms_segments"
USAGE_METRIC_AI = "ai_usage_units"
USAGE_METRIC_PAYMENTS = "payment_rail_events"
USAGE_METRIC_REPORTS = "report_generation_runs"


def record_usage_meter_increment(
    *,
    school,
    metric_code: str,
    quantity: int = 1,
    period_start=None,
    period_end=None,
    metadata: dict | None = None,
    ledger_sku_key: str | None = None,
    ledger_idempotency_key: str | None = None,
):
    """
    Roll up usage into apps.billing.UsageMeter for end-of-period invoicing.
    Optional marketplace ledger row when ``ledger_idempotency_key`` is provided (idempotent).
    """
    from apps.billing.models import UsageMeter
    from apps.billing.services import ensure_billing_account_for_school

    if quantity <= 0:
        return None
    account, _ = ensure_billing_account_for_school(school)
    now = timezone.now().date()
    p0 = period_start or now.replace(day=1)
    p1 = period_end or now
    meter, created = UsageMeter.objects.get_or_create(
        billing_account=account,
        school=school,
        metric_code=metric_code,
        period_start=p0,
        period_end=p1,
        defaults={"quantity": 0, "metadata": metadata or {}},
    )
    meter.quantity = int(meter.quantity or 0) + int(quantity)
    meta = dict(meter.metadata or {})
    if metadata:
        meta.update(metadata)
    meter.metadata = meta
    meter.save(update_fields=["quantity", "metadata", "updated_at"])
    if ledger_idempotency_key:
        try:
            from apps.marketplace.marketplace_sku_registry import get_contract
            from apps.marketplace.monetization_ledger_ops import append_usage_ledger

            sku = ledger_sku_key or "platform_ai_usage"
            contract = get_contract(sku)
            if contract is not None:
                sku = contract.sku_key
            append_usage_ledger(
                school=school,
                metric_code=metric_code,
                quantity=int(quantity),
                sku_key=sku,
                idempotency_key=ledger_idempotency_key[:180],
            )
        except (ImportError, AttributeError, TypeError, ValueError):
            pass
    return meter


def get_founder_marketplace_snapshot(*, days: int = 30) -> dict[str, Any]:
    """
    Aggregates for founder dashboard (no fabricated revenue).
    """
    from apps.billing.models import TenantSubscription, UsageMeter

    cutoff = timezone.now() - timedelta(days=days)
    active_ms = TenantMarketplaceSubscription.objects.filter(
        status=TenantMarketplaceSubscription.Status.ACTIVE,
        unit_amount__gt=0,
    )
    mrr_apps = Decimal("0.00")
    for row in active_ms.select_related("app"):
        amt = Decimal(str(row.unit_amount or "0"))
        if row.billing_interval == MarketplaceApp.BillingInterval.MONTHLY:
            mrr_apps += amt
        elif row.billing_interval == MarketplaceApp.BillingInterval.ANNUAL:
            mrr_apps += _annual_to_monthly(amt)

    core_qs = TenantSubscription.objects.filter(
        status__in=[
            TenantSubscription.Status.ACTIVE,
            TenantSubscription.Status.TRIALING,
            TenantSubscription.Status.PAST_DUE,
        ]
    )
    mrr_core = Decimal("0.00")
    for sub in core_qs.iterator(chunk_size=500):
        amt = Decimal(str(sub.billed_amount or sub.base_amount or "0"))
        if sub.billing_cycle == TenantSubscription.BillingCycle.MONTHLY:
            mrr_core += amt
        elif sub.billing_cycle == TenantSubscription.BillingCycle.ANNUAL:
            mrr_core += _annual_to_monthly(amt)

    fees = PlatformMarketplaceEarning.objects.filter(recorded_at__gte=cutoff).aggregate(
        total=Sum("platform_fee_amount"),
        gross=Sum("gross_amount"),
    )
    marketplace_fee_30d = fees.get("total") or Decimal("0.00")
    marketplace_gross_30d = fees.get("gross") or Decimal("0.00")

    usage_rows = UsageMeter.objects.filter(updated_at__gte=cutoff).aggregate(
        n=Sum("quantity")
    )
    usage_events_30d = int(usage_rows.get("n") or 0)

    churn_ms = TenantMarketplaceSubscription.objects.filter(
        canceled_at__gte=cutoff,
        status=TenantMarketplaceSubscription.Status.CANCELED,
    ).count()

    churn_core = TenantSubscription.objects.filter(
        canceled_at__isnull=False,
        canceled_at__gte=cutoff,
    ).count()

    total_apps = MarketplaceApp.objects.count()
    priced_apps = MarketplaceApp.objects.exclude(
        pricing_model=MarketplaceApp.PricingModel.FREE
    ).count()
    coverage_pct = round((priced_apps / total_apps) * 100.0, 1) if total_apps else 0.0

    has_split_logged = PlatformMarketplaceEarning.objects.exists()
    has_paid_sub = active_ms.exists() or mrr_core > 0
    verdict = "REVENUE_READY" if (has_split_logged or has_paid_sub) else "NOT_READY"

    return {
        "mrr_marketplace_apps": str(mrr_apps.quantize(Decimal("0.01"))),
        "mrr_platform_core": str(mrr_core.quantize(Decimal("0.01"))),
        "mrr_combined": str((mrr_apps + mrr_core).quantize(Decimal("0.01"))),
        "marketplace_gross_30d": str(marketplace_gross_30d.quantize(Decimal("0.01"))),
        "marketplace_platform_fees_30d": str(marketplace_fee_30d.quantize(Decimal("0.01"))),
        "usage_meter_units_30d": usage_events_30d,
        "churn_marketplace_subs_30d": churn_ms,
        "churn_platform_subs_30d": churn_core,
        "catalog_priced_app_ratio_pct": coverage_pct,
        "monetization_verdict": verdict,
    }
