from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
import json
import logging

from django.db import models, transaction, DatabaseError, IntegrityError
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from apps.billing.models import (
    BillingAccount,
    Entitlement,
    PlatformBillingProcessorConfig,
    BillingProcessorSyncEvent,
    PlatformLedgerEntry,
    Quote,
    RevenueSharePayout,
    TenantSubscription,
    UsageMeter,
)
from apps.billing.processors import get_platform_billing_processor

logger = logging.getLogger(__name__)

_BILLING_INCIDENT_SOURCE = "billing.platform"
_PAYOUT_INCIDENT_SOURCE = "billing.revenue_share"


_ACCOUNT_STATUS_MAP = {
    "active": BillingAccount.Status.ACTIVE,
    "trial": BillingAccount.Status.TRIAL,
    "trialing": BillingAccount.Status.TRIAL,
    "past_due": BillingAccount.Status.PAST_DUE,
    "past due": BillingAccount.Status.PAST_DUE,
    "suspended": BillingAccount.Status.SUSPENDED,
    "canceled": BillingAccount.Status.CANCELED,
    "cancelled": BillingAccount.Status.CANCELED,
}

_ENTITLEMENT_ACTIVE_SUBSCRIPTION_STATUSES = {
    TenantSubscription.Status.TRIALING,
    TenantSubscription.Status.ACTIVE,
    TenantSubscription.Status.PAST_DUE,
}

_SUBSCRIPTION_STATUS_MAP = {
    "trial": TenantSubscription.Status.TRIALING,
    "trialing": TenantSubscription.Status.TRIALING,
    "active": TenantSubscription.Status.ACTIVE,
    "past_due": TenantSubscription.Status.PAST_DUE,
    "past due": TenantSubscription.Status.PAST_DUE,
    "suspended": TenantSubscription.Status.SUSPENDED,
    "canceled": TenantSubscription.Status.CANCELED,
    "cancelled": TenantSubscription.Status.CANCELED,
}


def _resolve_account_status(school) -> str:
    billing_type = getattr(school, "billing_type", "") or ""
    if billing_type == getattr(school.BillingType, "FREE_TRIAL", "FREE_TRIAL"):
        return BillingAccount.Status.TRIAL
    if getattr(school, "is_frozen", False):
        return BillingAccount.Status.SUSPENDED
    return BillingAccount.Status.ACTIVE


def _resolve_subscription_status(school) -> str:
    billing_type = getattr(school, "billing_type", "") or ""
    if billing_type == getattr(school.BillingType, "FREE_TRIAL", "FREE_TRIAL"):
        return TenantSubscription.Status.TRIALING
    if getattr(school, "is_frozen", False):
        return TenantSubscription.Status.SUSPENDED
    return TenantSubscription.Status.ACTIVE


def _normalize_status(
    raw_status: str | None, status_map: dict[str, str], default: str
) -> str:
    normalized = str(raw_status or "").strip().lower()
    if not normalized:
        return default
    return status_map.get(normalized, default)


def _cycle_delta(billing_cycle: str) -> timedelta | None:
    if billing_cycle == TenantSubscription.BillingCycle.ANNUAL:
        return timedelta(days=365)
    if billing_cycle == TenantSubscription.BillingCycle.MONTHLY:
        return timedelta(days=30)
    return None


def _subscription_amount(subscription: TenantSubscription) -> Decimal:
    billed_amount = Decimal(str(subscription.billed_amount or "0"))
    if billed_amount > 0:
        return billed_amount
    return Decimal(str(subscription.base_amount or "0")) + Decimal(
        str(subscription.addons_amount or "0")
    )


def _period_reference(
    subscription: TenantSubscription, period_start: datetime, period_end: datetime
) -> str:
    return (
        f"PLATFORM-{subscription.school_id}-{period_start:%Y%m%d}-{period_end:%Y%m%d}"
    )


def _current_balance_for_account(account: BillingAccount) -> Decimal:
    # tenant-isolation-allow: billing_account is the school-scoped FK; equivalent to `school=account.school` (reviewed 2026-05-14)
    totals = PlatformLedgerEntry.objects.filter(
        billing_account=account,
        status=PlatformLedgerEntry.Status.POSTED,
    ).aggregate(
        debits=models.Sum(
            models.Case(
                models.When(
                    entry_type__in=[
                        PlatformLedgerEntry.EntryType.CHARGE,
                        PlatformLedgerEntry.EntryType.ADJUSTMENT,
                    ],
                    then="amount",
                ),
                default=Decimal("0.00"),
                output_field=models.DecimalField(max_digits=12, decimal_places=2),
            )
        ),
        credits=models.Sum(
            models.Case(
                models.When(
                    entry_type__in=[
                        PlatformLedgerEntry.EntryType.CREDIT,
                        PlatformLedgerEntry.EntryType.WRITE_OFF,
                    ],
                    then="amount",
                ),
                default=Decimal("0.00"),
                output_field=models.DecimalField(max_digits=12, decimal_places=2),
            )
        ),
    )
    return Decimal(str(totals.get("debits") or "0")) - Decimal(
        str(totals.get("credits") or "0")
    )


def platform_account_balance(account: BillingAccount) -> Decimal:
    """Public read-only accessor for a billing account's current posted balance.

    Positive = the tenant owes the platform. Exposed so operator surfaces can
    display the balance without reaching into the private ledger aggregator.
    """
    return _current_balance_for_account(account)


def _coerce_datetime(value, default: datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return default


def _coerce_date(value, default: date | None = None) -> date | None:
    if isinstance(value, date):
        return value
    return default


def _json_safe(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def _normalize_entitlement_code(code: object) -> str:
    return str(code or "").strip().lower()


def _subscription_feature_codes(subscription: TenantSubscription) -> dict[str, str]:
    plan = getattr(subscription, "plan", None)
    codes: dict[str, str] = {}
    if plan and isinstance(getattr(plan, "included_features", None), list):
        for code in plan.included_features:
            normalized = _normalize_entitlement_code(code)
            if normalized:
                codes[normalized] = Entitlement.Source.PLAN
    for code in list(getattr(subscription, "addon_codes", None) or []):
        normalized = _normalize_entitlement_code(code)
        if normalized:
            codes[normalized] = Entitlement.Source.ADDON
    return codes


def _subscription_limit_codes(subscription: TenantSubscription) -> dict[str, int]:
    plan = getattr(subscription, "plan", None)
    if not plan:
        return {}
    limits: dict[str, int] = {}
    for code in ("max_students", "max_staff"):
        value = getattr(plan, code, None)
        if value is not None:
            limits[code] = int(value)
    return limits


def sync_subscription_entitlements(
    subscription: TenantSubscription, *, as_of: datetime | None = None
) -> list[str]:
    """
    Materialize subscription plan/add-on features and limits into Entitlement rows.
    Returns the entitlement codes touched.
    """
    as_of = as_of or timezone.now()
    school = subscription.school
    enabled = subscription.status in _ENTITLEMENT_ACTIVE_SUBSCRIPTION_STATUSES
    touched: list[str] = []
    desired_sources = _subscription_feature_codes(subscription)
    desired_limits = _subscription_limit_codes(subscription)

    for code, source in desired_sources.items():
        Entitlement.objects.update_or_create(
            school=school,
            code=code,
            defaults={
                "subscription": subscription,
                "kind": Entitlement.Kind.FEATURE,
                "source": source,
                "is_enabled": enabled,
                "limit_value": None,
                "effective_from": as_of,
                "effective_until": None if enabled else as_of,
                "metadata": {"subscription_id": subscription.pk},
            },
        )
        touched.append(code)

    for code, value in desired_limits.items():
        Entitlement.objects.update_or_create(
            school=school,
            code=code,
            defaults={
                "subscription": subscription,
                "kind": Entitlement.Kind.LIMIT,
                "source": Entitlement.Source.PLAN,
                "is_enabled": enabled,
                "limit_value": value,
                "effective_from": as_of,
                "effective_until": None if enabled else as_of,
                "metadata": {"subscription_id": subscription.pk},
            },
        )
        touched.append(code)

    stale_qs = Entitlement.objects.filter(
        school=school,
        subscription=subscription,
        source__in=[Entitlement.Source.PLAN, Entitlement.Source.ADDON],
    ).exclude(code__in=touched)
    stale_qs.update(is_enabled=False, effective_until=as_of)
    try:
        from apps.platform_runtime.entitlement_gates import invalidate_entitlement_cache

        invalidate_entitlement_cache(school)
    except (ImportError, AttributeError, TypeError):
        pass
    return touched


def convert_quote_to_contract(quote: Quote):
    """
    Convert an accepted quote into a live subscription (quote-to-contract flow).
    Ensures billing account and subscription for the quote's school using quote plan/amount.
    Idempotent: if quote already ACCEPTED, returns existing subscription.
    """
    if quote.status == Quote.Status.ACCEPTED:
        account, _ = ensure_billing_account_for_school(quote.school)
        subscription = (
            TenantSubscription.objects.filter(
                school=quote.school,
                billing_account=account,
                status__in=[
                    TenantSubscription.Status.TRIALING,
                    TenantSubscription.Status.ACTIVE,
                    TenantSubscription.Status.PAST_DUE,
                    TenantSubscription.Status.SUSPENDED,
                ],
            )
            .order_by("-updated_at")
            .first()
        )
        if subscription:
            return account, subscription
    if quote.status not in (Quote.Status.DRAFT, Quote.Status.SENT):
        raise ValueError(
            f"Quote must be DRAFT or SENT to convert; current status: {quote.status}"
        )
    if not quote.school_id:
        raise ValueError("Quote must have a school to convert to contract")
    with transaction.atomic():
        account, _ = ensure_billing_account_for_school(quote.school)
        period_start = timezone.now()
        billing_cycle = str(
            (quote.metadata or {}).get("billing_cycle")
            or TenantSubscription.BillingCycle.MONTHLY
        ).upper()
        if billing_cycle not in {
            TenantSubscription.BillingCycle.MONTHLY,
            TenantSubscription.BillingCycle.ANNUAL,
            TenantSubscription.BillingCycle.MANUAL,
        }:
            billing_cycle = TenantSubscription.BillingCycle.MONTHLY
        cycle_delta = _cycle_delta(billing_cycle) or timedelta(days=30)
        period_end = period_start + cycle_delta
        subscription = (
            TenantSubscription.objects.filter(
                school=quote.school,
                billing_account=account,
                status__in=[
                    TenantSubscription.Status.TRIALING,
                    TenantSubscription.Status.ACTIVE,
                    TenantSubscription.Status.PAST_DUE,
                    TenantSubscription.Status.SUSPENDED,
                ],
            )
            .order_by("-updated_at")
            .first()
        )
        amount = Decimal(str(quote.amount or "0"))
        school_changed = []
        if getattr(quote.school, "plan_id", None) != getattr(quote.plan, "pk", None):
            quote.school.plan = quote.plan
            school_changed.append("plan")
        if getattr(quote.school, "billing_type", "") != getattr(
            quote.school.BillingType, "REGULAR", "REGULAR"
        ):
            quote.school.billing_type = quote.school.BillingType.REGULAR
            school_changed.append("billing_type")
        if getattr(quote.school, "trial_end_date", None) is not None:
            quote.school.trial_end_date = None
            school_changed.append("trial_end_date")
        if school_changed:
            quote.school.save(update_fields=school_changed + ["updated_at"])
        if subscription:
            subscription.plan = quote.plan
            subscription.status = TenantSubscription.Status.ACTIVE
            subscription.billing_cycle = billing_cycle
            subscription.current_period_start = period_start
            subscription.current_period_end = period_end
            subscription.trial_end_date = None
            subscription.base_amount = amount
            subscription.billed_amount = amount
            subscription.metadata = {
                **(subscription.metadata or {}),
                "source": "quote_to_contract",
                "quote_id": quote.pk,
            }
            subscription.save(
                update_fields=[
                    "plan_id",
                    "status",
                    "billing_cycle",
                    "current_period_start",
                    "current_period_end",
                    "trial_end_date",
                    "base_amount",
                    "billed_amount",
                    "metadata",
                    "updated_at",
                ]
            )
        else:
            subscription = TenantSubscription.objects.create(
                billing_account=account,
                school=quote.school,
                plan=quote.plan,
                status=TenantSubscription.Status.ACTIVE,
                billing_cycle=billing_cycle,
                starts_at=period_start,
                current_period_start=period_start,
                current_period_end=period_end,
                base_amount=amount,
                billed_amount=amount,
                metadata={"source": "quote_to_contract", "quote_id": quote.pk},
            )
        # Ensure account currency matches quote if needed
        if quote.currency_code and account.currency_code != quote.currency_code:
            account.currency_code = quote.currency_code
        if account.status != BillingAccount.Status.ACTIVE:
            account.status = BillingAccount.Status.ACTIVE
        account.save(update_fields=["currency_code", "status", "updated_at"])
        reconcile_subscription_entitlements(subscription, as_of=period_start)
        sync_billing_incident_state(subscription)
        quote.status = Quote.Status.ACCEPTED
        quote.save(update_fields=["status", "updated_at"])
    return account, subscription


def ensure_billing_account_for_school(school):
    from apps.policies.policy_registry import get_effective_policy

    from django.conf import settings as _dj_settings
    policy = get_effective_policy(school)
    contact_email = str((policy.get("contact_email") or "") or "").strip()
    platform_default = getattr(_dj_settings, "PLATFORM_DEFAULT_CURRENCY", "USD")
    currency_code = platform_default
    default_region = getattr(school, "default_region", None)
    if default_region and getattr(default_region, "default_currency", None):
        currency_code = (
            str(default_region.default_currency).strip().upper()[:3] or platform_default
        )
    account, created = BillingAccount.objects.get_or_create(
        school=school,
        defaults={
            "status": _resolve_account_status(school),
            "billing_email": contact_email,
            "currency_code": currency_code,
        },
    )
    changed_fields = []
    desired_status = _resolve_account_status(school)
    if account.status != desired_status:
        account.status = desired_status
        changed_fields.append("status")
    if contact_email and account.billing_email != contact_email:
        account.billing_email = contact_email
        changed_fields.append("billing_email")
    if account.currency_code != currency_code:
        account.currency_code = currency_code
        changed_fields.append("currency_code")
    if changed_fields:
        account.save(update_fields=changed_fields + ["updated_at"])
    return account, created


def record_app_install_for_billing(school, app, installation, *, amount=None):
    """
    Record a tenant app install for billing (6.3 / 29.10). Creates a platform ledger entry
    so the install is visible for invoicing and add-on billing. Call from marketplace
    install_app after AppInstallation and AppAuditLog are created.
    amount: optional Decimal; if omitted, 0 (record-only until add-on pricing is configured).
    """
    if not school or not app:
        return None
    account, _ = ensure_billing_account_for_school(school)
    amt = amount if amount is not None else Decimal("0.00")
    app_name = getattr(app, "name", None) or (
        app.slug if hasattr(app, "slug") else str(app)
    )
    inst_id = getattr(installation, "id", None) or getattr(installation, "pk", "")
    ref = f"app_install_{inst_id}"
    entry = PlatformLedgerEntry.objects.create(
        billing_account=account,
        school=school,
        entry_type=PlatformLedgerEntry.EntryType.CHARGE,
        status=PlatformLedgerEntry.Status.POSTED,
        amount=amt,
        currency_code=account.currency_code,
        description=f"App install: {app_name}",
        reference=ref,
        source="marketplace_app_install",
        source_ref=str(inst_id),
        happened_at=timezone.now(),
        metadata={
            "app_slug": getattr(app, "slug", None),
            "installation_id": inst_id,
            "app_install_billing_record": True,
        },
    )
    return entry


def _resolve_country_multiplier_for_school(school) -> Decimal:
    """PPP multiplier from siteconfig.CountryMultiplier by school region/country code."""
    from apps.siteconfig.models_platform_catalog import CountryMultiplier

    candidates: list[str] = []
    region = getattr(school, "default_region", None)
    if region is not None:
        code = str(getattr(region, "code", "") or "").strip().upper()
        if code:
            candidates.append(code)
            if len(code) >= 2:
                candidates.append(code[:2])
    for lookup in candidates:
        row = (
            CountryMultiplier.objects.filter(country_code__iexact=lookup, is_active=True)
            .order_by("-updated_at")
            .first()
        )
        if row is not None:
            return Decimal(str(row.multiplier))
    return Decimal("1.000")


def ensure_subscription_for_school(school):
    account, _created = ensure_billing_account_for_school(school)
    active_statuses = [
        TenantSubscription.Status.TRIALING,
        TenantSubscription.Status.ACTIVE,
        TenantSubscription.Status.PAST_DUE,
        TenantSubscription.Status.SUSPENDED,
    ]
    subscription = (
        TenantSubscription.objects.filter(
            school=school, billing_account=account, status__in=active_statuses
        )
        .order_by("-updated_at", "-created_at")
        .first()
    )
    # Bind the platform default plan (Free) for a brand-new tenant that has no
    # explicit plan, so Free-tier entitlements + usage limits apply from day one.
    # This sets School.plan (the FK the usage-limit middleware reads — a plan-less
    # school otherwise skips all caps), not just the subscription's plan. Scoped
    # to first subscription creation: never override an existing tenant's plan
    # (an established plan-less tenant keeps its current posture). Operators set
    # which plan is the default via Plan.is_default; tenants can still upgrade.
    if subscription is None and getattr(school, "plan_id", None) is None:
        try:
            from apps.siteconfig.models_platform_catalog import Plan

            default_plan = Plan.get_default_plan()
            if default_plan is not None:
                school.plan = default_plan
                school.save(update_fields=["plan", "updated_at"])
        except (ImportError, AttributeError, TypeError, ValueError, DatabaseError, IntegrityError):
            logger.warning(
                "default-plan binding skipped for school %s",
                getattr(school, "id", None),
                exc_info=True,
            )
    period_start = timezone.now()
    period_end = period_start + timedelta(days=30)
    desired_status = _resolve_subscription_status(school)
    base_amount = Decimal(
        str(getattr(getattr(school, "plan", None), "base_price", None) or "0")
    )
    country_multiplier = _resolve_country_multiplier_for_school(school)
    billed_amount = (base_amount * country_multiplier).quantize(Decimal("0.01"))
    if subscription is None:
        subscription = TenantSubscription.objects.create(
            billing_account=account,
            school=school,
            plan=getattr(school, "plan", None),
            status=desired_status,
            starts_at=period_start,
            current_period_start=period_start,
            current_period_end=period_end,
            trial_end_date=getattr(school, "trial_end_date", None),
            base_amount=base_amount,
            country_multiplier=country_multiplier,
            billed_amount=billed_amount,
            addon_codes=list(getattr(school, "addons", None) or []),
            metadata={"seeded_from_school": True},
        )
        try:
            from apps.schools.funnel_events import record_subscription_started_billing

            record_subscription_started_billing(
                school,
                subscription_id=subscription.pk,
                billed_amount=str(billed_amount),
            )
        except (ImportError, AttributeError, TypeError, ValueError):
            pass
        reconcile_subscription_entitlements(subscription, as_of=period_start)
        return account, subscription, True
    changed_fields = []
    if subscription.plan_id != getattr(getattr(school, "plan", None), "pk", None):
        subscription.plan = getattr(school, "plan", None)
        changed_fields.append("plan")
    if subscription.status != desired_status:
        subscription.status = desired_status
        changed_fields.append("status")
    if subscription.trial_end_date != getattr(school, "trial_end_date", None):
        subscription.trial_end_date = getattr(school, "trial_end_date", None)
        changed_fields.append("trial_end_date")
    addon_codes = list(getattr(school, "addons", None) or [])
    if subscription.addon_codes != addon_codes:
        subscription.addon_codes = addon_codes
        changed_fields.append("addon_codes")
    if subscription.base_amount != base_amount:
        subscription.base_amount = base_amount
        changed_fields.append("base_amount")
    if subscription.country_multiplier != country_multiplier:
        subscription.country_multiplier = country_multiplier
        changed_fields.append("country_multiplier")
    if (
        not subscription.external_subscription_ref
        and subscription.billed_amount != billed_amount
    ):
        subscription.billed_amount = billed_amount
        changed_fields.append("billed_amount")
    if changed_fields:
        subscription.save(update_fields=changed_fields + ["updated_at"])
        reconcile_subscription_entitlements(subscription)
    return account, subscription, False


def reconcile_subscription_entitlements(
    subscription: TenantSubscription, *, as_of: datetime | None = None
):
    as_of = as_of or timezone.now()
    school = subscription.school
    account = subscription.billing_account
    school_changed = []
    account_changed = []

    if (
        school.billing_type == school.BillingType.FREE_TRIAL
        and subscription.trial_end_date
        and subscription.trial_end_date < as_of.date()
    ):
        school.billing_type = school.BillingType.REGULAR
        school_changed.append("billing_type")

    if subscription.status == TenantSubscription.Status.TRIALING:
        target_account_status = BillingAccount.Status.TRIAL
    elif subscription.status == TenantSubscription.Status.PAST_DUE:
        target_account_status = BillingAccount.Status.PAST_DUE
    elif subscription.status == TenantSubscription.Status.SUSPENDED:
        target_account_status = BillingAccount.Status.SUSPENDED
    elif subscription.status == TenantSubscription.Status.CANCELED:
        target_account_status = BillingAccount.Status.CANCELED
    else:
        target_account_status = BillingAccount.Status.ACTIVE

    if account.status != target_account_status:
        account.status = target_account_status
        account_changed.append("status")

    if subscription.status == TenantSubscription.Status.SUSPENDED:
        if not school.is_frozen:
            school.is_frozen = True
            school_changed.append("is_frozen")
        if school.frozen_reason != "BILLING":
            school.frozen_reason = "BILLING"
            school_changed.append("frozen_reason")
    elif school.frozen_reason == "BILLING":
        if school.is_frozen:
            school.is_frozen = False
            school_changed.append("is_frozen")
        school.frozen_reason = ""
        school_changed.append("frozen_reason")

    if account_changed:
        account.save(update_fields=account_changed + ["updated_at"])
    if school_changed:
        school.save(update_fields=school_changed + ["updated_at"])
    sync_subscription_entitlements(subscription, as_of=as_of)
    return account, school


def sync_billing_incident_state(subscription: TenantSubscription):
    from apps.observability.incident_services import (
        resolve_platform_incident,
        upsert_platform_incident,
    )
    from apps.observability.models import PlatformIncident

    school = subscription.school
    incident_key = f"billing-delinquency:{school.pk}"
    if subscription.status in {
        TenantSubscription.Status.PAST_DUE,
        TenantSubscription.Status.SUSPENDED,
    }:
        severity = (
            PlatformIncident.Severity.CRITICAL
            if subscription.status == TenantSubscription.Status.SUSPENDED
            else PlatformIncident.Severity.HIGH
        )
        summary = (
            "Platform subscription is suspended and tenant access is at risk."
            if subscription.status == TenantSubscription.Status.SUSPENDED
            else "Platform subscription is past due and requires operator follow-up."
        )
        upsert_platform_incident(
            incident_key=incident_key,
            title=f"Billing delinquency: {school.name}",
            incident_type=PlatformIncident.IncidentType.BILLING,
            severity=severity,
            summary=summary,
            source_system=_BILLING_INCIDENT_SOURCE,
            affected_school=school,
            affected_schema_name=getattr(school, "schema_name", "")
            or getattr(school, "subdomain", ""),
            details={
                "subscription_status": subscription.status,
                "account_status": subscription.billing_account.status,
                "trial_end_date": subscription.trial_end_date.isoformat()
                if subscription.trial_end_date
                else None,
                "current_period_end": (
                    subscription.current_period_end.isoformat()
                    if subscription.current_period_end
                    else None
                ),
                "external_subscription_ref": subscription.external_subscription_ref,
            },
        )
        return

    resolve_platform_incident(
        incident_key=incident_key,
        source_system=_BILLING_INCIDENT_SOURCE,
        incident_type="billing",
        affected_school=school,
    )


def sync_platform_usage_snapshot(school):
    account, _subscription, _ = ensure_subscription_for_school(school)
    now = timezone.now().date()
    period_start = now.replace(day=1)
    if period_start.month == 12:
        period_end = period_start.replace(
            year=period_start.year + 1, month=1
        ) - timedelta(days=1)
    else:
        period_end = period_start.replace(month=period_start.month + 1) - timedelta(
            days=1
        )

    from apps.schools.models import TenantApiUsage

    total_api_calls = (
        TenantApiUsage.objects.filter(
            school=school, period_date__gte=period_start, period_date__lte=period_end
        )
        .aggregate(total=models.Sum("request_count"))
        .get("total")
        or 0
    )
    meter, _created = UsageMeter.objects.update_or_create(
        billing_account=account,
        school=school,
        metric_code="api_calls",
        period_start=period_start,
        period_end=period_end,
        defaults={
            "quantity": int(total_api_calls),
            "metadata": {"source": "schools.TenantApiUsage"},
        },
    )
    return meter


def record_platform_charge(
    *,
    school,
    amount,
    entry_type: str = PlatformLedgerEntry.EntryType.CHARGE,
    description: str = "",
    reference: str = "",
    source: str = "",
    source_ref: str = "",
    metadata: dict | None = None,
):
    account, _subscription, _ = ensure_subscription_for_school(school)
    return PlatformLedgerEntry.objects.create(
        billing_account=account,
        school=school,
        entry_type=entry_type,
        amount=Decimal(str(amount)),
        currency_code=account.currency_code,
        description=description,
        reference=reference,
        source=source,
        source_ref=source_ref,
        happened_at=timezone.now(),
        metadata=metadata or {},
    )


def apply_processor_snapshot(
    *,
    school,
    processor_code: str,
    event_type: str,
    account_status: str | None = None,
    subscription_status: str | None = None,
    external_customer_ref: str = "",
    external_subscription_ref: str = "",
    currency_code: str | None = None,
    billed_amount: Decimal | str | None = None,
    current_period_start: datetime | None = None,
    current_period_end: datetime | None = None,
    trial_end_date: date | None = None,
    happened_at: datetime | None = None,
    payload: dict | None = None,
    message: str = "",
    processor_source_ref: str = "",
):
    with transaction.atomic():
        account, subscription, _ = ensure_subscription_for_school(school)
        happened_at = _coerce_datetime(happened_at, timezone.now())
        account_changed = []
        subscription_changed = []

        normalized_account_status = _normalize_status(
            account_status, _ACCOUNT_STATUS_MAP, account.status
        )
        normalized_subscription_status = _normalize_status(
            subscription_status,
            _SUBSCRIPTION_STATUS_MAP,
            subscription.status,
        )

        if account.processor_code != processor_code:
            account.processor_code = processor_code
            account_changed.append("processor_code")
        if (
            external_customer_ref
            and account.external_customer_ref != external_customer_ref
        ):
            account.external_customer_ref = external_customer_ref
            account_changed.append("external_customer_ref")
        if currency_code and account.currency_code != currency_code:
            account.currency_code = currency_code
            account_changed.append("currency_code")
        if account.status != normalized_account_status:
            account.status = normalized_account_status
            account_changed.append("status")
        if account.last_processor_sync_at != happened_at:
            account.last_processor_sync_at = happened_at
            account_changed.append("last_processor_sync_at")

        if (
            external_subscription_ref
            and subscription.external_subscription_ref != external_subscription_ref
        ):
            subscription.external_subscription_ref = external_subscription_ref
            subscription_changed.append("external_subscription_ref")
        if subscription.status != normalized_subscription_status:
            subscription.status = normalized_subscription_status
            subscription_changed.append("status")
        if billed_amount is not None:
            normalized_amount = Decimal(str(billed_amount))
            if subscription.billed_amount != normalized_amount:
                subscription.billed_amount = normalized_amount
                subscription_changed.append("billed_amount")
        period_start = _coerce_datetime(
            current_period_start, subscription.current_period_start or timezone.now()
        )
        period_end = _coerce_datetime(
            current_period_end, subscription.current_period_end or period_start
        )
        if subscription.current_period_start != period_start:
            subscription.current_period_start = period_start
            subscription_changed.append("current_period_start")
        if subscription.current_period_end != period_end:
            subscription.current_period_end = period_end
            subscription_changed.append("current_period_end")
        normalized_trial_end = _coerce_date(trial_end_date, subscription.trial_end_date)
        if subscription.trial_end_date != normalized_trial_end:
            subscription.trial_end_date = normalized_trial_end
            subscription_changed.append("trial_end_date")
        if (
            normalized_subscription_status == TenantSubscription.Status.CANCELED
            and subscription.canceled_at != happened_at
        ):
            subscription.canceled_at = happened_at
            subscription_changed.append("canceled_at")

        if account_changed:
            account.save(update_fields=account_changed + ["updated_at"])
        if subscription_changed:
            subscription.save(update_fields=subscription_changed + ["updated_at"])
        reconcile_subscription_entitlements(subscription, as_of=happened_at)

        event = BillingProcessorSyncEvent.objects.create(
            school=school,
            billing_account=account,
            subscription=subscription,
            processor_code=processor_code,
            event_type=event_type,
            status=BillingProcessorSyncEvent.Status.APPLIED,
            external_customer_ref=external_customer_ref
            or account.external_customer_ref,
            external_subscription_ref=external_subscription_ref
            or subscription.external_subscription_ref,
            payload=_json_safe(payload or {}),
            message=message,
            happened_at=happened_at,
        )
        sync_billing_incident_state(subscription)

        et = str(event_type or "").strip().lower()
        _PROC_PAYMENT_OK = frozenset(
            {
                "invoice.paid",
                "invoice.payment_succeeded",
                "checkout.session.completed",
            }
        )
        _PROC_PAYMENT_FAIL = frozenset(
            {
                "invoice.payment_failed",
                "charge.failed",
                "payment_intent.payment_failed",
            }
        )
        if et in _PROC_PAYMENT_OK or et in _PROC_PAYMENT_FAIL:
            from apps.schools.funnel_events import record_payment_outcome_signal

            record_payment_outcome_signal(
                school,
                success=et in _PROC_PAYMENT_OK,
                metadata={
                    "processor_code": processor_code,
                    "billing_event_type": event_type,
                    "processor_source_ref": processor_source_ref,
                },
            )

        # Audit C4 — bridge the processor's payment-failed event to the
        # platform Email Matrix. Billing emits provider-specific strings
        # ("invoice.payment_failed", "payment_intent.payment_failed", ...);
        # the matrix keys on the canonical "tenant.payment.failed", so without
        # this bridge no dunning / payment-failed email ever fired (operators
        # OR tenants). Best-effort: never break webhook processing on a mail
        # publish failure.
        if et in _PROC_PAYMENT_FAIL:
            try:
                from apps.platform_runtime.event_bus import publish_event

                publish_event(
                    "tenant.payment.failed",
                    {
                        "school_name": getattr(school, "name", "")
                        or getattr(school, "slug", ""),
                        "billing_event_type": event_type,
                        "processor_code": processor_code,
                    },
                    school_id=getattr(school, "id", None),
                    idempotency_key=(
                        f"pay_failed:{processor_code}:"
                        f"{processor_source_ref or external_subscription_ref or account.pk}"
                    ),
                )
            except Exception:  # noqa: BLE001 — mail publish never breaks billing
                logger.warning(
                    "billing.payment_failed_event_publish_failed school_id=%s",
                    getattr(school, "id", None),
                )
        if billed_amount is not None:
            try:
                amt = Decimal(str(billed_amount))
            except (TypeError, ValueError, ArithmeticError):
                amt = Decimal("0")
            if amt > 0 and et in (
                "invoice.paid",
                "invoice.payment_succeeded",
                "checkout.session.completed",
            ):
                src_ref = str(processor_source_ref or "").strip()
                ref = f"{processor_code}:{et}:{src_ref or external_subscription_ref or account.pk}"
                # tenant-isolation-allow: webhook idempotency check by unique reference (reviewed 2026-05-14)
                if not PlatformLedgerEntry.objects.filter(
                    reference=ref, source="stripe_webhook"
                ).exists():
                    record_platform_charge(
                        school=school,
                        amount=amt,
                        description=f"Stripe-compatible payment ({event_type})",
                        reference=ref,
                        source="stripe_webhook",
                        source_ref=src_ref or str(external_subscription_ref or ""),
                        metadata={"event_type": event_type, "processor": processor_code},
                    )
                    try:
                        from apps.marketplace.monetization import (
                            USAGE_METRIC_PAYMENTS,
                            record_usage_meter_increment,
                        )

                        record_usage_meter_increment(
                            school=school,
                            metric_code=USAGE_METRIC_PAYMENTS,
                            quantity=1,
                            metadata={
                                "source": "apply_processor_snapshot",
                                "event_type": event_type,
                            },
                        )
                    except (AttributeError, DatabaseError, ImportError, TypeError, ValueError):
                        logger.debug(
                            "payment rail usage meter rollup skipped", exc_info=True
                        )

        _promote_school_plan_from_processor_payload(
            school,
            subscription,
            event_type=et,
            payload=payload,
        )
        return event, account, subscription


def _promote_school_plan_from_processor_payload(
    school,
    subscription,
    *,
    event_type: str,
    payload: dict | None,
) -> None:
    """After platform-plan checkout, align ``school.plan`` + subscription plan FK."""
    if school is None or subscription is None:
        return
    et = str(event_type or "").strip().lower()
    if et not in ("checkout.session.completed", "customer.subscription.updated"):
        return
    raw_payload = payload if isinstance(payload, dict) else {}
    data = raw_payload.get("data") if isinstance(raw_payload.get("data"), dict) else {}
    obj = data.get("object") if isinstance(data.get("object"), dict) else {}
    metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
    if metadata.get("billing_context") == "marketplace_addon":
        return
    plan_code = str(metadata.get("plan_code") or "").strip()
    if not plan_code:
        return
    try:
        from apps.plans_entitlements.models import Plan

        target = Plan.objects.filter(slug=plan_code, is_active=True).first()
        if target is None:
            return
        school_changed: list[str] = []
        promoted = False
        if getattr(school, "plan_id", None) != target.pk:
            school.plan = target
            school_changed.append("plan")
        if school_changed:
            school.save(update_fields=school_changed + ["updated_at"])
            promoted = True
        if subscription.plan_id != target.pk:
            subscription.plan = target
            subscription.save(update_fields=["plan", "updated_at"])
            promoted = True
        if promoted:
            # The plan FK alone does not change what the tenant can actually use:
            # feature gates read materialized Entitlement rows behind a cached gate.
            # Reconcile re-materializes those rows + busts the gate cache so the
            # upgraded plan takes effect immediately instead of healing only on the
            # next cache TTL or a manual lifecycle run.
            reconcile_subscription_entitlements(subscription)
    except (ImportError, AttributeError, TypeError, ValueError, DatabaseError):
        logger.warning("billing_plan_promotion_failed", exc_info=True)


_MARKETPLACE_PAYMENT_EVENTS = frozenset(
    {
        "checkout.session.completed",
        "invoice.paid",
        "invoice.payment_succeeded",
    }
)


def finalize_marketplace_addon_payment(
    school,
    snapshot: dict | None,
    *,
    processor_code: str,
):
    """
    After a billing webhook succeeds for Stripe Checkout metadata including
    marketplace_app_id, persist publisher revenue share intent and entitled module SKUs.

    Safe to call repeatedly for the same Stripe session/idempotency markers.
    """
    if school is None or not snapshot:
        return None

    evt = str(snapshot.get("event_type") or "").strip().lower()
    if evt not in _MARKETPLACE_PAYMENT_EVENTS:
        return None

    raw_mid = snapshot.get("marketplace_app_id")
    if raw_mid is None:
        payload = snapshot.get("payload") if isinstance(snapshot.get("payload"), dict) else {}
        obj = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        nested_obj = obj.get("object") if isinstance(obj.get("object"), dict) else {}
        nested_meta = (
            nested_obj.get("metadata") if isinstance(nested_obj.get("metadata"), dict) else {}
        )
        raw_mid = nested_meta.get("marketplace_app_id")

    session_ref = str(snapshot.get("processor_source_ref") or "").strip()

    try:
        app_pk = int(raw_mid)
    except (TypeError, ValueError):
        return None

    from apps.marketplace.manifest_schema import normalize_platform_manifest
    from apps.marketplace.models import MarketplaceApp

    try:
        app = MarketplaceApp.objects.select_related("publisher", "listing").get(
            pk=app_pk, is_active=True
        )
    except MarketplaceApp.DoesNotExist:
        return None

    listing = getattr(app, "listing", None)
    pub = getattr(app, "publisher", None)

    publisher_slug = getattr(pub, "slug", "") if pub else ""
    publisher_name = getattr(pub, "name", "") if pub else ""
    rev_pct = Decimal("0")
    if listing is not None:
        rev_pct = Decimal(str(listing.revenue_share_percent or "0")).quantize(Decimal("0.01"))

    pub_slug_manifest = publisher_slug or ""
    merged_manifest = normalize_platform_manifest(
        dict(app.manifest or {}),
        app_slug=app.slug,
        app_name=app.name,
        version=app.version or "",
        publisher_slug=pub_slug_manifest,
    )
    sku_code = str(merged_manifest.get("billing_sku") or "").strip()

    amt_raw = snapshot.get("billed_amount")
    amt = Decimal("0")
    try:
        if amt_raw is not None:
            amt = Decimal(str(amt_raw)).quantize(Decimal("0.01"))
    except (ArithmeticError, TypeError, ValueError):
        amt = Decimal("0")

    entitlement_codes: list[str] = []
    if sku_code:
        entitlement_codes.append(sku_code.strip().lower())
    for rf in merged_manifest.get("required_features") or []:
        code = str(rf).strip().lower()
        if code and code not in entitlement_codes:
            entitlement_codes.append(code)

    addon_changed = False
    with transaction.atomic():
        locked = type(school).objects.select_for_update().get(pk=school.pk)
        merged = [a for a in (list(getattr(locked, "addons", None) or [])) if a]
        for c in entitlement_codes:
            if c not in merged:
                merged.append(c)
                addon_changed = True
        if addon_changed:
            locked.addons = merged
            locked.save(update_fields=["addons", "updated_at"])

    from django.conf import settings as _dj_settings
    _platform_curr = getattr(_dj_settings, "PLATFORM_DEFAULT_CURRENCY", "USD")
    curr = str(snapshot.get("currency_code") or "").strip().upper()
    if len(curr) != 3:
        acct_row = BillingAccount.objects.filter(school_id=school.pk).first()
        curr = str(getattr(acct_row, "currency_code", None) or _platform_curr).strip().upper()[:3]

    publisher_share_recorded = False
    if rev_pct > 0 and pub and amt > 0 and session_ref:
        share = (amt * (rev_pct / Decimal("100"))).quantize(Decimal("0.01"))
        if share > 0:
            pcode = str(processor_code).strip()
            payout_dup = False
            for rp in RevenueSharePayout.objects.filter(
                processor_code=pcode,
                source_school_id=school.pk,
            ).order_by("-pk")[:80]:
                meta = rp.metadata if isinstance(rp.metadata, dict) else {}
                if (
                    str(meta.get("marketplace_addon_session_ref") or "") == session_ref
                    and str(meta.get("marketplace_app_id") or "") == str(app.pk)
                ):
                    payout_dup = True
                    break
            if not payout_dup:
                pname = publisher_name or publisher_slug or (
                    getattr(pub, "name", "") if pub else ""
                )
                pref = publisher_slug or (str(pub.pk) if pub else "")
                RevenueSharePayout.objects.create(
                    source_school=school,
                    payout_scope=RevenueSharePayout.Scope.APP_PUBLISHER,
                    status=RevenueSharePayout.Status.DRAFT,
                    payee_name=str(pname or "Publisher")[:160],
                    payee_ref=str(pref or "unknown")[:120],
                    processor_code=pcode[:32],
                    gross_amount=amt,
                    fee_amount=Decimal("0.00"),
                    net_amount=share,
                    currency_code=curr,
                    metadata={
                        "marketplace_addon_session_ref": session_ref,
                        "marketplace_app_id": str(app.pk),
                        "revenue_share_percent": str(rev_pct),
                        "billing_sku": sku_code,
                        "publisher_slug": publisher_slug,
                    },
                )
                publisher_share_recorded = True

    try:
        from apps.marketplace.monetization_ledger_ops import (
            append_payment_success_ledger,
            infer_production_psp_for_ledger,
        )

        pay_ref = session_ref or str(snapshot.get("processor_source_ref") or "").strip()
        if pay_ref and amt > 0:
            prod = infer_production_psp_for_ledger(school, snapshot, processor_code)
            append_payment_success_ledger(
                school=school,
                app=app,
                amount=amt,
                currency=curr,
                processor_ref=pay_ref,
                processor_code=str(processor_code or "")[:32],
                production_psp=prod,
            )
    except (ImportError, AttributeError, TypeError, ValueError):
        pass

    return {
        "status": "applied",
        "addon_codes_updated": entitlement_codes if addon_changed else [],
        "publisher_share_recorded": publisher_share_recorded,
    }


def run_platform_billing_lifecycle(
    *,
    as_of: datetime | None = None,
    grace_days: int = 7,
    suspension_days: int = 30,
):
    as_of = as_of or timezone.now()
    summary = {
        "trial_converted": 0,
        "charges_created": 0,
        "renewed": 0,
        "past_due": 0,
        "suspended": 0,
        "restored": 0,
    }
    subscriptions = list(
        TenantSubscription.objects.select_related(
            "school", "billing_account", "plan"
        ).filter(
            status__in=[
                TenantSubscription.Status.TRIALING,
                TenantSubscription.Status.ACTIVE,
                TenantSubscription.Status.PAST_DUE,
                TenantSubscription.Status.SUSPENDED,
            ]
        )
    )
    for subscription in subscriptions:
        school = subscription.school
        account = subscription.billing_account
        subscription_changed = []
        account_changed = []
        cycle_delta = _cycle_delta(subscription.billing_cycle)
        due_anchor = (
            subscription.current_period_end
            or subscription.current_period_start
            or as_of
        )

        expired_trial = (
            subscription.trial_end_date and subscription.trial_end_date < as_of.date()
        )
        if expired_trial and (
            school.billing_type == school.BillingType.FREE_TRIAL
            or subscription.status == TenantSubscription.Status.TRIALING
        ):
            if school.billing_type == school.BillingType.FREE_TRIAL:
                school.billing_type = school.BillingType.REGULAR
                school.save(update_fields=["billing_type", "updated_at"])
            if subscription.status == TenantSubscription.Status.TRIALING:
                subscription.status = TenantSubscription.Status.ACTIVE
                subscription_changed.append("status")
            summary["trial_converted"] += 1

        if (
            cycle_delta
            and subscription.current_period_end
            and subscription.current_period_end <= as_of
        ):
            period_start = (
                subscription.current_period_start
                or subscription.starts_at
                or subscription.current_period_end
            )
            period_end = subscription.current_period_end
            reference = _period_reference(subscription, period_start, period_end)
            # tenant-isolation-allow: billing_account FK already school-scoped (reviewed 2026-05-14)
            if not PlatformLedgerEntry.objects.filter(
                billing_account=account,
                reference=reference,
                status=PlatformLedgerEntry.Status.POSTED,
            ).exists():
                amount = _subscription_amount(subscription)
                if amount > 0:
                    record_platform_charge(
                        school=school,
                        amount=amount,
                        description=f"Platform subscription renewal {period_start:%Y-%m-%d} to {period_end:%Y-%m-%d}",
                        reference=reference,
                        source="billing_lifecycle",
                        metadata={
                            "period_start": period_start.isoformat(),
                            "period_end": period_end.isoformat(),
                        },
                    )
                    summary["charges_created"] += 1
            subscription.last_invoiced_at = as_of
            subscription.current_period_start = period_end
            subscription.current_period_end = period_end + cycle_delta
            subscription_changed.extend(
                ["last_invoiced_at", "current_period_start", "current_period_end"]
            )
            summary["renewed"] += 1

        balance = _current_balance_for_account(account)
        overdue_threshold = due_anchor + timedelta(days=grace_days)
        suspension_threshold = overdue_threshold + timedelta(
            days=max(suspension_days - grace_days, 0)
        )

        if balance > 0 and as_of >= overdue_threshold:
            if account.delinquent_since is None:
                account.delinquent_since = overdue_threshold
                account_changed.append("delinquent_since")
            if as_of >= suspension_threshold:
                if subscription.status != TenantSubscription.Status.SUSPENDED:
                    subscription.status = TenantSubscription.Status.SUSPENDED
                    subscription_changed.append("status")
                    summary["suspended"] += 1
            elif subscription.status not in {
                TenantSubscription.Status.PAST_DUE,
                TenantSubscription.Status.SUSPENDED,
            }:
                subscription.status = TenantSubscription.Status.PAST_DUE
                subscription_changed.append("status")
                summary["past_due"] += 1
        elif balance <= 0:
            target_status = (
                TenantSubscription.Status.TRIALING
                if school.billing_type == school.BillingType.FREE_TRIAL
                and subscription.trial_end_date
                and subscription.trial_end_date >= as_of.date()
                else TenantSubscription.Status.ACTIVE
            )
            if subscription.status in {
                TenantSubscription.Status.PAST_DUE,
                TenantSubscription.Status.SUSPENDED,
            }:
                subscription.status = target_status
                subscription_changed.append("status")
                summary["restored"] += 1
            if account.delinquent_since is not None:
                account.delinquent_since = None
                account_changed.append("delinquent_since")

        if account_changed:
            account.save(update_fields=account_changed + ["updated_at"])
        if subscription_changed:
            subscription.save(
                update_fields=list(dict.fromkeys(subscription_changed + ["updated_at"]))
            )
        reconcile_subscription_entitlements(subscription, as_of=as_of)
        sync_billing_incident_state(subscription)

    return summary


def schedule_revenue_share_payout(
    *,
    payee_name: str,
    gross_amount,
    fee_amount=Decimal("0.00"),
    payout_scope: str = RevenueSharePayout.Scope.APP_PUBLISHER,
    payee_ref: str = "",
    processor_code: str = "",
    external_payout_ref: str = "",
    currency_code: str | None = None,
    source_school=None,
    period_start: date | None = None,
    period_end: date | None = None,
    scheduled_for: datetime | None = None,
    metadata: dict | None = None,
):
    # Resolve currency at call time from PLATFORM_DEFAULT_CURRENCY setting (was hardcoded "USD").
    if not currency_code:
        from django.conf import settings as _dj_settings
        currency_code = getattr(_dj_settings, "PLATFORM_DEFAULT_CURRENCY", "USD")
    gross_amount = Decimal(str(gross_amount))
    fee_amount = Decimal(str(fee_amount))
    net_amount = gross_amount - fee_amount
    return RevenueSharePayout.objects.create(
        source_school=source_school,
        payout_scope=payout_scope,
        status=RevenueSharePayout.Status.SCHEDULED,
        payee_name=payee_name,
        payee_ref=payee_ref,
        processor_code=processor_code,
        external_payout_ref=external_payout_ref,
        period_start=period_start,
        period_end=period_end,
        gross_amount=gross_amount,
        fee_amount=fee_amount,
        net_amount=net_amount,
        currency_code=currency_code,
        scheduled_for=scheduled_for or timezone.now(),
        metadata=metadata or {},
    )


def _normalize_payout_execution_status(raw_status: str | None) -> str:
    normalized = str(raw_status or "").strip().lower()
    if normalized in {"paid", "succeeded", "completed"}:
        return RevenueSharePayout.Status.PAID
    if normalized in {"submitted", "queued", "pending", "processing", "in_transit"}:
        return RevenueSharePayout.Status.IN_TRANSIT
    if normalized in {"failed", "error", "rejected"}:
        return RevenueSharePayout.Status.FAILED
    return RevenueSharePayout.Status.IN_TRANSIT


def _record_payout_sync_event(
    *,
    payout: RevenueSharePayout,
    status: str,
    event_type: str,
    message: str = "",
    payload: dict | None = None,
):
    account = None
    subscription = None
    if payout.source_school_id:
        account = BillingAccount.objects.filter(school=payout.source_school).first()
        if account is not None:
            subscription = (
                TenantSubscription.objects.filter(
                    billing_account=account, school=payout.source_school
                )
                .order_by("-updated_at", "-created_at")
                .first()
            )
    return BillingProcessorSyncEvent.objects.create(
        school=payout.source_school,
        billing_account=account,
        subscription=subscription,
        processor_code=str(payout.processor_code or "").strip() or "manual",
        event_type=event_type,
        status=status,
        payload=_json_safe(payload or {}),
        message=message[:255],
        happened_at=timezone.now(),
    )


def _sync_revenue_share_payout_incident_state(
    payout: RevenueSharePayout, *, error_message: str = ""
):
    from apps.observability.incident_services import (
        resolve_platform_incident,
        upsert_platform_incident,
    )
    from apps.observability.models import PlatformIncident

    incident_key = f"revenue-share-payout:{payout.pk}"
    if payout.status == RevenueSharePayout.Status.FAILED:
        upsert_platform_incident(
            incident_key=incident_key,
            title=f"Revenue-share payout failed: {payout.payee_name}",
            incident_type=PlatformIncident.IncidentType.BILLING,
            severity=PlatformIncident.Severity.HIGH,
            summary=error_message
            or "A scheduled revenue-share payout could not be executed.",
            source_system=_PAYOUT_INCIDENT_SOURCE,
            affected_school=payout.source_school,
            affected_schema_name=(
                getattr(payout.source_school, "schema_name", "")
                or getattr(payout.source_school, "subdomain", "")
            ),
            details={
                "payout_id": payout.pk,
                "payee_name": payout.payee_name,
                "payee_ref": payout.payee_ref,
                "processor_code": payout.processor_code,
                "external_payout_ref": payout.external_payout_ref,
                "payout_scope": payout.payout_scope,
                "status": payout.status,
            },
        )
        return

    resolve_platform_incident(
        incident_key=incident_key,
        source_system=_PAYOUT_INCIDENT_SOURCE,
        incident_type="billing",
        affected_school=payout.source_school,
    )


def execute_revenue_share_payout(
    payout,
    *,
    executed_at: datetime | None = None,
    force: bool = False,
    http_post_json=None,
    http_post_form=None,
):
    if not isinstance(payout, RevenueSharePayout):
        payout = RevenueSharePayout.objects.get(pk=payout)
    executed_at = executed_at or timezone.now()

    if payout.status in {
        RevenueSharePayout.Status.PAID,
        RevenueSharePayout.Status.VOIDED,
    }:
        return payout, {
            "status": "skipped",
            "message": "Payout is already finalized.",
            "skipped": True,
        }
    if not force and payout.scheduled_for and payout.scheduled_for > executed_at:
        return payout, {
            "status": "skipped",
            "message": "Payout is not due yet.",
            "skipped": True,
        }

    error_message = ""
    try:
        processor_code = str(payout.processor_code or "").strip().lower()
        if not processor_code:
            raise ValueError("Payout processor is not configured.")
        config = PlatformBillingProcessorConfig.objects.filter(
            code=processor_code, is_active=True
        ).first()
        if config is None:
            raise ValueError(
                f"Platform billing processor '{processor_code}' is not configured."
            )

        processor = get_platform_billing_processor(config)
        result = processor.execute_payout(
            payout,
            http_post_json=http_post_json,
            http_post_form=http_post_form,
        )
        payout_status = _normalize_payout_execution_status(result.get("status"))
        metadata = dict(payout.metadata or {})
        metadata["last_execution"] = {
            "executed_at": executed_at.isoformat(),
            "processor_code": processor_code,
            "status": str(result.get("status") or ""),
            "message": str(result.get("message") or ""),
        }
        metadata["processor_response"] = result.get("payload") or {}
        metadata.pop("last_error", None)
        payout.metadata = metadata
        payout.status = payout_status
        payout.scheduled_for = None
        if result.get("external_payout_ref"):
            payout.external_payout_ref = str(result["external_payout_ref"])
        if payout_status == RevenueSharePayout.Status.PAID:
            payout.paid_at = executed_at
        payout.save(
            update_fields=[
                "status",
                "scheduled_for",
                "external_payout_ref",
                "paid_at",
                "metadata",
                "updated_at",
            ]
        )
        _record_payout_sync_event(
            payout=payout,
            status=BillingProcessorSyncEvent.Status.APPLIED,
            event_type="payout.executed",
            message=str(result.get("message") or ""),
            payload={
                "payout_id": payout.pk,
                "processor_status": result.get("status"),
                "external_payout_ref": payout.external_payout_ref,
                "response": result.get("payload") or {},
            },
        )
        _sync_revenue_share_payout_incident_state(payout)
        return payout, result
    except (
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        DatabaseError,
        ConnectionError,
        OSError,
    ) as exc:
        error_message = str(exc).strip() or "Payout execution failed."
        logger.warning(
            "Payout execution failed: payout_id=%s processor_code=%s error=%s",
            payout.pk,
            getattr(payout, "processor_code", None),
            error_message,
            exc_info=True,
        )
        metadata = dict(payout.metadata or {})
        metadata["last_error"] = {
            "at": executed_at.isoformat(),
            "processor_code": str(payout.processor_code or ""),
            "message": error_message,
        }
        payout.metadata = metadata
        payout.status = RevenueSharePayout.Status.FAILED
        payout.scheduled_for = None
        payout.save(update_fields=["status", "scheduled_for", "metadata", "updated_at"])
        _record_payout_sync_event(
            payout=payout,
            status=BillingProcessorSyncEvent.Status.FAILED,
            event_type="payout.failed",
            message=error_message,
            payload={"payout_id": payout.pk, "error": error_message},
        )
        _sync_revenue_share_payout_incident_state(payout, error_message=error_message)
        return payout, {"status": "failed", "message": error_message}


def run_revenue_share_payout_execution(
    *,
    as_of: datetime | None = None,
    limit: int = 50,
    include_failed: bool = False,
    http_post_json=None,
    http_post_form=None,
):
    as_of = as_of or timezone.now()
    statuses = [RevenueSharePayout.Status.SCHEDULED]
    if include_failed:
        statuses.append(RevenueSharePayout.Status.FAILED)
    payouts = list(
        RevenueSharePayout.objects.filter(status__in=statuses)
        .filter(
            models.Q(scheduled_for__isnull=True) | models.Q(scheduled_for__lte=as_of)
        )
        .select_related("source_school")
        .order_by("scheduled_for", "created_at")[: max(1, int(limit))]
    )
    summary = {
        "selected": len(payouts),
        "paid": 0,
        "in_transit": 0,
        "failed": 0,
        "skipped": 0,
    }
    for payout in payouts:
        payout, result = execute_revenue_share_payout(
            payout,
            executed_at=as_of,
            force=include_failed,
            http_post_json=http_post_json,
            http_post_form=http_post_form,
        )
        if result.get("skipped"):
            summary["skipped"] += 1
            continue
        if payout.status == RevenueSharePayout.Status.PAID:
            summary["paid"] += 1
        elif payout.status == RevenueSharePayout.Status.IN_TRANSIT:
            summary["in_transit"] += 1
        elif payout.status == RevenueSharePayout.Status.FAILED:
            summary["failed"] += 1
    return summary


def sync_stripe_connect_from_webhook_snapshot(*, school, snapshot: dict) -> bool:
    """Persist Stripe Connect account object from billing webhook snapshot."""
    account_obj = snapshot.get("stripe_connect_account")
    if not isinstance(account_obj, dict) or not school:
        return False
    try:
        from apps.schools.stripe_connect_settings import merge_stripe_account_object

        merge_stripe_account_object(school, account_obj)
        school.save(update_fields=["settings"])
        return True
    except (AttributeError, TypeError, ValueError):
        return False


def convert_quote_to_subscription(quote_id: int):
    """
    Commercial platform (29.10): convert an accepted Quote to TenantSubscription.
    Connection point: when external sign/contract flow is ready, implement this to create
    BillingAccount (if needed), TenantSubscription from quote.plan/amount, and set quote.status = ACCEPTED.
    Returns (success: bool, message: str).
    """
    try:
        quote = Quote.objects.select_related("school", "plan").get(pk=quote_id)
    except Quote.DoesNotExist:
        return False, "Quote not found"

    try:
        convert_quote_to_contract(quote)
    except ValueError as exc:
        return False, str(exc)

    return True, "Quote converted to subscription."


# ---------------------------------------------------------------------------
# Alternative Payment Methods (APMs) — wizard-driven enablement
# ---------------------------------------------------------------------------


def enable_apm(school, apm_key: str) -> bool:
    """Mark an Alternative Payment Method as enabled for ``school``.

    Persists into ``BillingAccount.metadata["enabled_apms"]`` (list, deduped,
    stable order). Returns ``True`` on a state change, ``False`` if already
    enabled or no-op (missing school / blank key).

    Idempotent. Safe to call repeatedly from wizard re-runs.
    """
    if school is None or not apm_key:
        return False
    apm_key = str(apm_key).strip()
    if not apm_key:
        return False

    account, _ = BillingAccount.objects.get_or_create(
        school=school,
        defaults={"status": _resolve_account_status(school)},
    )
    metadata = account.metadata or {}
    if not isinstance(metadata, dict):
        metadata = {}
    enabled = list(metadata.get("enabled_apms") or [])
    if apm_key in enabled:
        return False
    enabled.append(apm_key)
    metadata["enabled_apms"] = enabled
    account.metadata = metadata
    account.save(update_fields=["metadata", "updated_at"])
    logger.info("billing.enable_apm: school_id=%s apm_key=%s", school.pk, apm_key)
    return True


def set_payment_settings(
    school,
    *,
    settlement_country: str | None = None,
    settlement_currency: str | None = None,
    settlement_bank_account_alias: str | None = None,
) -> bool:
    """Persist settlement-corridor settings into ``BillingAccount`` + metadata.

    ``currency_code`` lands on the column (3-char ISO); the rest go into
    metadata. Idempotent: returns ``True`` only on actual state change.
    """
    if school is None:
        return False
    account, _ = BillingAccount.objects.get_or_create(
        school=school,
        defaults={"status": _resolve_account_status(school)},
    )
    currency_changed = False
    metadata_changed = False
    if settlement_currency:
        cc = str(settlement_currency).strip().upper()
        if len(cc) == 3 and cc != account.currency_code:
            account.currency_code = cc
            currency_changed = True

    metadata = account.metadata or {}
    if not isinstance(metadata, dict):
        metadata = {}
    settlement = dict(metadata.get("settlement") or {})
    for key, value in (
        ("country", settlement_country),
        ("bank_account_alias", settlement_bank_account_alias),
    ):
        if value:
            value = str(value).strip()
            if value and settlement.get(key) != value:
                settlement[key] = value
                metadata_changed = True
    if metadata_changed:
        metadata["settlement"] = settlement
        account.metadata = metadata

    if not (currency_changed or metadata_changed):
        return False
    update_fields = ["updated_at"]
    if currency_changed:
        update_fields.insert(0, "currency_code")
    if metadata_changed:
        update_fields.insert(0, "metadata")
    account.save(update_fields=update_fields)
    logger.info(
        "billing.set_payment_settings: school_id=%s currency=%s country=%s",
        school.pk, settlement_currency, settlement_country,
    )
    return True


def compute_subscription_price_for_school(
    school,
    plan,
    *,
    student_count: int | None = None,
) -> "dict":
    """v4.00.36 — apply PPP multiplier + VAT to a Plan's base price for a tenant.

    Reads the plan's base price (FLAT or PER_STUDENT × students), resolves
    the tenant's country_code, and runs the amount through the canonical
    regional pricing helper. Returns a serialisable dict::

        {
          "subtotal": Decimal, "tax": Decimal, "total": Decimal,
          "currency_code": str, "multiplier": Decimal, "tax_rate": Decimal,
          "tax_code": str, "country_code": str, "billing_model": str,
        }

    Falls back to base USD when ``school`` or ``plan`` is missing — never
    raises into the request path.
    """
    if school is None or plan is None:
        return {
            "subtotal": Decimal("0.00"), "tax": Decimal("0.00"), "total": Decimal("0.00"),
            "currency_code": "USD", "multiplier": Decimal("1"), "tax_rate": Decimal("0"),
            "tax_code": "", "country_code": "", "billing_model": "FLAT",
            "sku_override_applied": False,
        }

    billing_model = (getattr(plan, "billing_model", "") or "FLAT").upper()
    base_price = Decimal("0.00")
    try:
        if billing_model == "PER_STUDENT" and plan.price_per_student:
            count = max(0, int(student_count or 0))
            base_price = Decimal(str(plan.price_per_student)) * Decimal(count)
        elif billing_model == "TIERED" and isinstance(plan.tier_rules, list):
            count = max(0, int(student_count or 0))
            base_price = Decimal("0.00")
            for band in plan.tier_rules:
                if not isinstance(band, dict):
                    continue
                band_max = int(band.get("max") or 0)
                if count <= band_max or band_max == 0:
                    base_price = Decimal(str(band.get("price") or 0))
                    break
        else:
            base_price = Decimal(str(plan.base_price or 0))
    except (AttributeError, TypeError, ValueError):
        base_price = Decimal("0.00")

    try:
        from apps.billing.regional_pricing import compute_localized_price

        country_code = (getattr(school, "country_code", "") or "").upper()
        # B2: a per-country Plan SKU override reprices this market explicitly.
        sku_override = None
        try:
            resolver = getattr(plan, "regional_sku_override_for", None)
            if callable(resolver):
                sku_override = resolver(country_code)
        except (AttributeError, TypeError, ValueError):
            sku_override = None
        localized = compute_localized_price(
            base_price, country_code, sku_override=sku_override
        )
    except (ImportError, RuntimeError):
        localized = None
    if localized is None:
        return {
            "subtotal": base_price.quantize(Decimal("0.01")),
            "tax": Decimal("0.00"),
            "total": base_price.quantize(Decimal("0.01")),
            "currency_code": "USD",
            "multiplier": Decimal("1"),
            "tax_rate": Decimal("0"),
            "tax_code": "",
            "country_code": "",
            "billing_model": billing_model,
            "sku_override_applied": False,
        }
    return {
        "subtotal": localized.subtotal,
        "tax": localized.tax,
        "total": localized.total,
        "currency_code": localized.currency_code,
        "multiplier": localized.multiplier,
        "tax_rate": localized.tax_rate,
        "tax_code": localized.tax_code,
        "country_code": localized.country_code,
        "billing_model": billing_model,
        "sku_override_applied": localized.sku_override_applied,
    }
