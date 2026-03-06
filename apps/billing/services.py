from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import models, transaction
from django.utils import timezone

from apps.billing.models import (
    BillingAccount,
    BillingProcessorSyncEvent,
    PlatformLedgerEntry,
    RevenueSharePayout,
    TenantSubscription,
    UsageMeter,
)


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


def _normalize_status(raw_status: str | None, status_map: dict[str, str], default: str) -> str:
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
    return Decimal(str(subscription.base_amount or "0")) + Decimal(str(subscription.addons_amount or "0"))


def _period_reference(subscription: TenantSubscription, period_start: datetime, period_end: datetime) -> str:
    return f"PLATFORM-{subscription.school_id}-{period_start:%Y%m%d}-{period_end:%Y%m%d}"


def _current_balance_for_account(account: BillingAccount) -> Decimal:
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
    return Decimal(str(totals.get("debits") or "0")) - Decimal(str(totals.get("credits") or "0"))


def _coerce_datetime(value, default: datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return default


def _coerce_date(value, default: date | None = None) -> date | None:
    if isinstance(value, date):
        return value
    return default


def ensure_billing_account_for_school(school):
    contact_email = ""
    if isinstance(getattr(school, "settings", None), dict):
        contact_email = str(school.settings.get("contact_email") or "").strip()
    currency_code = "USD"
    default_region = getattr(school, "default_region", None)
    if default_region and getattr(default_region, "default_currency", None):
        currency_code = str(default_region.default_currency).strip().upper()[:3] or "USD"
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


def ensure_subscription_for_school(school):
    account, _created = ensure_billing_account_for_school(school)
    active_statuses = [
        TenantSubscription.Status.TRIALING,
        TenantSubscription.Status.ACTIVE,
        TenantSubscription.Status.PAST_DUE,
        TenantSubscription.Status.SUSPENDED,
    ]
    subscription = (
        TenantSubscription.objects.filter(school=school, billing_account=account, status__in=active_statuses)
        .order_by("-updated_at", "-created_at")
        .first()
    )
    period_start = timezone.now()
    period_end = period_start + timedelta(days=30)
    desired_status = _resolve_subscription_status(school)
    base_amount = Decimal(str(getattr(getattr(school, "plan", None), "base_price", None) or "0"))
    billed_amount = base_amount
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
            billed_amount=billed_amount,
            addon_codes=list(getattr(school, "addons", None) or []),
            metadata={"seeded_from_school": True},
        )
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
    if not subscription.external_subscription_ref and subscription.billed_amount != billed_amount:
        subscription.billed_amount = billed_amount
        changed_fields.append("billed_amount")
    if changed_fields:
        subscription.save(update_fields=changed_fields + ["updated_at"])
    return account, subscription, False


def reconcile_subscription_entitlements(subscription: TenantSubscription, *, as_of: datetime | None = None):
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
    return account, school


def sync_platform_usage_snapshot(school):
    account, _subscription, _ = ensure_subscription_for_school(school)
    now = timezone.now().date()
    period_start = now.replace(day=1)
    if period_start.month == 12:
        period_end = period_start.replace(year=period_start.year + 1, month=1) - timedelta(days=1)
    else:
        period_end = period_start.replace(month=period_start.month + 1) - timedelta(days=1)

    from apps.schools.models import TenantApiUsage

    total_api_calls = (
        TenantApiUsage.objects.filter(school=school, period_date__gte=period_start, period_date__lte=period_end)
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
        defaults={"quantity": int(total_api_calls), "metadata": {"source": "schools.TenantApiUsage"}},
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
):
    with transaction.atomic():
        account, subscription, _ = ensure_subscription_for_school(school)
        happened_at = _coerce_datetime(happened_at, timezone.now())
        account_changed = []
        subscription_changed = []

        normalized_account_status = _normalize_status(account_status, _ACCOUNT_STATUS_MAP, account.status)
        normalized_subscription_status = _normalize_status(
            subscription_status,
            _SUBSCRIPTION_STATUS_MAP,
            subscription.status,
        )

        if account.processor_code != processor_code:
            account.processor_code = processor_code
            account_changed.append("processor_code")
        if external_customer_ref and account.external_customer_ref != external_customer_ref:
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

        if external_subscription_ref and subscription.external_subscription_ref != external_subscription_ref:
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
        period_start = _coerce_datetime(current_period_start, subscription.current_period_start or timezone.now())
        period_end = _coerce_datetime(current_period_end, subscription.current_period_end or period_start)
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
        if normalized_subscription_status == TenantSubscription.Status.CANCELED and subscription.canceled_at != happened_at:
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
            external_customer_ref=external_customer_ref or account.external_customer_ref,
            external_subscription_ref=external_subscription_ref or subscription.external_subscription_ref,
            payload=payload or {},
            message=message,
            happened_at=happened_at,
        )
        return event, account, subscription


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
        TenantSubscription.objects.select_related("school", "billing_account", "plan").filter(
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
        due_anchor = subscription.current_period_end or subscription.current_period_start or as_of

        if (
            school.billing_type == school.BillingType.FREE_TRIAL
            and subscription.trial_end_date
            and subscription.trial_end_date < as_of.date()
        ):
            school.billing_type = school.BillingType.REGULAR
            school.save(update_fields=["billing_type", "updated_at"])
            if subscription.status == TenantSubscription.Status.TRIALING:
                subscription.status = TenantSubscription.Status.ACTIVE
                subscription_changed.append("status")
            summary["trial_converted"] += 1

        if cycle_delta and subscription.current_period_end and subscription.current_period_end <= as_of:
            period_start = subscription.current_period_start or subscription.starts_at or subscription.current_period_end
            period_end = subscription.current_period_end
            reference = _period_reference(subscription, period_start, period_end)
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
                        metadata={"period_start": period_start.isoformat(), "period_end": period_end.isoformat()},
                    )
                    summary["charges_created"] += 1
            subscription.last_invoiced_at = as_of
            subscription.current_period_start = period_end
            subscription.current_period_end = period_end + cycle_delta
            subscription_changed.extend(["last_invoiced_at", "current_period_start", "current_period_end"])
            summary["renewed"] += 1

        balance = _current_balance_for_account(account)
        overdue_threshold = due_anchor + timedelta(days=grace_days)
        suspension_threshold = overdue_threshold + timedelta(days=max(suspension_days - grace_days, 0))

        if balance > 0 and as_of >= overdue_threshold:
            if account.delinquent_since is None:
                account.delinquent_since = overdue_threshold
                account_changed.append("delinquent_since")
            if as_of >= suspension_threshold:
                if subscription.status != TenantSubscription.Status.SUSPENDED:
                    subscription.status = TenantSubscription.Status.SUSPENDED
                    subscription_changed.append("status")
                    summary["suspended"] += 1
            elif subscription.status not in {TenantSubscription.Status.PAST_DUE, TenantSubscription.Status.SUSPENDED}:
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
            if subscription.status in {TenantSubscription.Status.PAST_DUE, TenantSubscription.Status.SUSPENDED}:
                subscription.status = target_status
                subscription_changed.append("status")
                summary["restored"] += 1
            if account.delinquent_since is not None:
                account.delinquent_since = None
                account_changed.append("delinquent_since")

        if account_changed:
            account.save(update_fields=account_changed + ["updated_at"])
        if subscription_changed:
            subscription.save(update_fields=list(dict.fromkeys(subscription_changed + ["updated_at"])))
        reconcile_subscription_entitlements(subscription, as_of=as_of)

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
    currency_code: str = "USD",
    source_school=None,
    period_start: date | None = None,
    period_end: date | None = None,
    scheduled_for: datetime | None = None,
    metadata: dict | None = None,
):
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
