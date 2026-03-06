from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.billing.models import BillingAccount, PlatformLedgerEntry, TenantSubscription, UsageMeter


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
            base_amount=Decimal(str(getattr(getattr(school, "plan", None), "base_price", None) or "0")),
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
    base_amount = Decimal(str(getattr(getattr(school, "plan", None), "base_price", None) or "0"))
    if subscription.base_amount != base_amount:
        subscription.base_amount = base_amount
        changed_fields.append("base_amount")
    if changed_fields:
        subscription.save(update_fields=changed_fields + ["updated_at"])
    return account, subscription, False


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
