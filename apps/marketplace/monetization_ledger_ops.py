"""
Uniform marketplace monetization ledger writes (idempotent, tenant-scoped).

Settlement posture is honest: test contexts and missing PSP readiness never emit
``settlement_completed`` without a real processor signal elsewhere (webhooks).
"""

from __future__ import annotations

import sys
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction

from apps.marketplace.models import MarketplaceApp, MarketplaceMonetizationLedgerEntry


def _running_under_unittest() -> bool:
    return getattr(settings, "RUNNING_TESTS", False) or ("test" in sys.argv)


def classify_settlement_lane(school) -> dict:
    """
    Return ledger-facing lane + truth flags (never asserts live PSP success).

    - ``test_mode``: unittest / explicit billing test metadata.
    - ``external_blocked``: corridor/readiness not READY for inbound tuition settlements.
    - ``pending_external``: customer exists but settlement confirmation happens via PSP webhooks.
    - ``internal``: bookkeeping-only rows (no PSP rail required).
    """
    from apps.billing.models import BillingAccount
    from apps.billing.regional_payment_readiness import compute_payment_readiness
    from apps.finance.models import ComplianceProfile

    if _running_under_unittest():
        return {
            "lane": "test_mode",
            "reason": "unittest_or_argv_test",
            "production_psp": False,
            "readiness_tier": None,
        }

    acct = BillingAccount.objects.filter(school=school).first()
    meta = dict(getattr(acct, "metadata", None) or {})
    if meta.get("billing_test_mode") or meta.get("stripe_test_mode"):
        return {
            "lane": "test_mode",
            "reason": "billing_account_metadata_test_flags",
            "production_psp": False,
            "readiness_tier": None,
        }

    compliance = ComplianceProfile.objects.filter(school=school).first()
    snap = compute_payment_readiness(school, compliance)
    tier = str(snap.get("tier") or "").strip().upper()

    ext_cust = (getattr(acct, "external_customer_ref", None) or "").strip() if acct else ""
    proc = (getattr(acct, "processor_code", None) or "").strip().lower() if acct else ""

    if tier == "MISSING_SETUP":
        return {
            "lane": "external_blocked",
            "reason": "payment_readiness_missing_setup",
            "production_psp": False,
            "readiness_tier": tier,
        }
    if tier == "FALLBACK_ONLY":
        return {
            "lane": "pending_external",
            "reason": "fallback_only_manual_corridor",
            "production_psp": False,
            "readiness_tier": tier,
        }
    if ext_cust and proc:
        return {
            "lane": "pending_external",
            "reason": "processor_customer_present_webhook_settles",
            "production_psp": True,
            "readiness_tier": tier or "READY",
        }
    return {
        "lane": "external_blocked",
        "reason": "no_processor_customer_for_settlement_rail",
        "production_psp": False,
        "readiness_tier": tier or None,
    }


def _emit_marketplace_platform_event(event_name: str, payload: dict, *, school, idempotency_key: str):
    try:
        from apps.platform_runtime.event_bus import publish_event

        publish_event(
            event_name,
            payload,
            tenant_id=str(school.pk),
            school_id=school.pk,
            idempotency_key=idempotency_key[:128],
        )
    except (AttributeError, ImportError, TypeError, ValueError):
        pass


@transaction.atomic
def append_marketplace_ledger_entry(
    *,
    school,
    event_type: str,
    sku_key: str = "",
    quantity: int = 1,
    amount: Decimal | None = None,
    currency: str = "USD",
    platform_fee_amount: Decimal | None = None,
    provider_reference: str = "",
    app: MarketplaceApp | None = None,
    installation=None,
    settlement_dependency: str = MarketplaceMonetizationLedgerEntry.SettlementDependency.EXTERNAL_PSP,
    status: str = MarketplaceMonetizationLedgerEntry.EntryStatus.POSTED,
    idempotency_key: str,
    metadata: dict | None = None,
    emit_event: str | None = None,
) -> MarketplaceMonetizationLedgerEntry:
    """
    Idempotent insert — returns existing row for (school, idempotency_key).
    """
    amt = amount if amount is not None else Decimal("0.00")
    pf = platform_fee_amount if platform_fee_amount is not None else Decimal("0.00")
    key = idempotency_key[:180]
    md = dict(metadata or {})

    existing = MarketplaceMonetizationLedgerEntry.objects.filter(
        school=school,
        idempotency_key=key,
    ).first()
    if existing:
        return existing

    row = MarketplaceMonetizationLedgerEntry(
        school=school,
        event_type=event_type,
        sku_key=(sku_key or "")[:80],
        quantity=int(quantity),
        amount=amt,
        currency=(currency or "USD")[:3],
        platform_fee_amount=pf,
        provider_reference=(provider_reference or "")[:255],
        status=status,
        settlement_dependency=settlement_dependency,
        idempotency_key=key,
        metadata=md,
        app=app,
        installation=installation,
    )
    try:
        row.save()
    except IntegrityError:
        return MarketplaceMonetizationLedgerEntry.objects.get(
            school=school,
            idempotency_key=key,
        )

    if emit_event:
        base_payload = {
            "school_id": str(school.pk),
            "sku_key": sku_key,
            "ledger_event_type": event_type,
            "amount": str(amt),
            "currency": row.currency,
            "production_psp_hint": md.get("production_psp"),
        }
        if app:
            base_payload["app_slug"] = app.slug
        _emit_marketplace_platform_event(
            emit_event,
            base_payload,
            school=school,
            idempotency_key=f"evt:{key}"[:128],
        )

    return row


def append_install_ledger_slice(
    *,
    school,
    app: MarketplaceApp,
    installation,
    charge: Decimal,
    listing,
    currency_code: str = "USD",
    settlement_snapshot: dict | None = None,
) -> None:
    settlement_snapshot = settlement_snapshot or classify_settlement_lane(school)
    lane = settlement_snapshot.get("lane")
    sku = "mkt_app_subscription"
    if app.pricing_model == MarketplaceApp.PricingModel.USAGE:
        sku = "mkt_app_usage"
    curr = (currency_code or "USD")[:3]

    append_marketplace_ledger_entry(
        school=school,
        event_type=MarketplaceMonetizationLedgerEntry.EventType.INSTALL,
        sku_key=sku,
        quantity=1,
        amount=charge,
        currency=curr,
        app=app,
        installation=installation,
        idempotency_key=f"mkt_led_inst:{school.pk}:{installation.pk}",
        metadata={
            "pricing_model": app.pricing_model,
            "install_charge": str(charge),
            "settlement_lane": lane,
        },
        emit_event=None,
    )

    append_marketplace_ledger_entry(
        school=school,
        event_type=MarketplaceMonetizationLedgerEntry.EventType.SUBSCRIPTION_STARTED,
        sku_key=sku,
        quantity=1,
        amount=Decimal("0.00"),
        currency=curr,
        app=app,
        installation=installation,
        idempotency_key=f"mkt_led_substart:{school.pk}:{installation.pk}",
        metadata={"pricing_model": app.pricing_model},
        emit_event="marketplace_subscription_started",
    )

    if lane == "test_mode":
        evt = MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_PENDING_EXTERNAL
        reason = "test_context_no_live_settlement_claim"
    elif lane == "external_blocked":
        evt = MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_EXTERNAL_BLOCKED
        reason = settlement_snapshot.get("reason")
    elif lane == "pending_external":
        evt = MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_PENDING_EXTERNAL
        reason = settlement_snapshot.get("reason")
    else:
        evt = MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_PENDING_EXTERNAL
        reason = settlement_snapshot.get("reason")

    append_marketplace_ledger_entry(
        school=school,
        event_type=evt,
        sku_key=sku,
        quantity=0,
        amount=Decimal("0.00"),
        currency=curr,
        app=app,
        installation=installation,
        idempotency_key=f"mkt_led_settle:{school.pk}:{installation.pk}",
        metadata={
            "lane": lane,
            "reason": reason,
            "readiness_tier": settlement_snapshot.get("readiness_tier"),
            "production_psp": settlement_snapshot.get("production_psp"),
        },
        emit_event="marketplace_settlement_blocked"
        if evt == MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_EXTERNAL_BLOCKED
        else None,
    )


def append_platform_fee_ledger(
    *,
    school,
    app: MarketplaceApp | None,
    installation,
    gross: Decimal,
    platform_fee: Decimal,
    currency: str,
    listing,
) -> None:
    append_marketplace_ledger_entry(
        school=school,
        event_type=MarketplaceMonetizationLedgerEntry.EventType.PLATFORM_FEE_RECORDED,
        sku_key="mkt_app_subscription",
        quantity=1,
        amount=gross,
        currency=currency,
        platform_fee_amount=platform_fee,
        app=app,
        installation=installation,
        idempotency_key=f"mkt_led_pf:{school.pk}:{installation.pk}",
        metadata={
            "listing_id": str(listing.pk) if listing else "",
            "revenue_share_percent": str(getattr(listing, "revenue_share_percent", "") or ""),
        },
        emit_event="marketplace_platform_fee_recorded",
    )


def append_uninstall_ledger(*, school, app: MarketplaceApp, installation) -> None:
    append_marketplace_ledger_entry(
        school=school,
        event_type=MarketplaceMonetizationLedgerEntry.EventType.UNINSTALL,
        sku_key="mkt_app_subscription",
        quantity=1,
        amount=Decimal("0.00"),
        app=app,
        installation=installation,
        idempotency_key=f"mkt_led_uninst:{school.pk}:{installation.pk}:{installation.uninstalled_at.isoformat() if installation.uninstalled_at else installation.pk}",
        metadata={"uninstalled": True},
        emit_event="marketplace_app_uninstalled",
    )


def append_usage_ledger(
    *,
    school,
    metric_code: str,
    quantity: int,
    sku_key: str = "platform_ai_usage",
    idempotency_key: str | None = None,
) -> MarketplaceMonetizationLedgerEntry:
    key = idempotency_key or f"mkt_usage:{school.pk}:{metric_code}:{sku_key}"
    return append_marketplace_ledger_entry(
        school=school,
        event_type=MarketplaceMonetizationLedgerEntry.EventType.USAGE_RECORDED,
        sku_key=sku_key,
        quantity=quantity,
        amount=Decimal("0.00"),
        idempotency_key=key[:180],
        metadata={"metric_code": metric_code},
        emit_event="marketplace_usage_recorded",
    )


def infer_production_psp_for_ledger(
    school,
    snapshot: dict | None,
    processor_code: str,
) -> bool:
    """
    Webhook / processor snapshot must not mark live settlement True for relay or test harnesses.
    """
    if _running_under_unittest():
        return False
    pc = (processor_code or "").strip().lower()
    if pc in ("relay", "test", "mock", "fake"):
        return False
    if not snapshot or not isinstance(snapshot, dict):
        return bool(classify_settlement_lane(school).get("production_psp"))
    pl = snapshot.get("payload")
    if isinstance(pl, dict):
        data = pl.get("data")
        if isinstance(data, dict):
            obj = data.get("object")
            if isinstance(obj, dict) and "livemode" in obj:
                return bool(obj.get("livemode"))
    return bool(classify_settlement_lane(school).get("production_psp"))


def append_payment_success_ledger(
    *,
    school,
    app: MarketplaceApp | None,
    amount: Decimal,
    currency: str,
    processor_ref: str,
    processor_code: str,
    production_psp: bool,
) -> MarketplaceMonetizationLedgerEntry | None:
    if not school:
        return None
    md = {
        "processor_code": processor_code,
        "production_psp": production_psp,
    }
    evt_pay = append_marketplace_ledger_entry(
        school=school,
        event_type=MarketplaceMonetizationLedgerEntry.EventType.PAYMENT_SUCCESS,
        sku_key="mkt_app_subscription",
        quantity=1,
        amount=amount,
        currency=currency,
        provider_reference=processor_ref[:255],
        app=app,
        idempotency_key=f"mkt_pay_ok:{school.pk}:{processor_ref}"[:190],
        metadata=md,
        emit_event="marketplace_payment_success",
    )
    settle_type = (
        MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_COMPLETED
        if production_psp
        else MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_PENDING_EXTERNAL
    )
    append_marketplace_ledger_entry(
        school=school,
        event_type=settle_type,
        sku_key="mkt_app_subscription",
        quantity=0,
        amount=amount,
        currency=currency,
        provider_reference=processor_ref[:255],
        app=app,
        idempotency_key=f"mkt_settle_pay:{school.pk}:{processor_ref}"[:190],
        metadata={
            "follows_payment_ledger_id": evt_pay.pk,
            "production_psp": production_psp,
        },
        emit_event=None,
    )
    return evt_pay
