"""Renewal / expiry reminder publisher (Part F).

The ``tenant.subscription.expiring_soon`` event and its admin email template
both existed but had NO publisher, so tenants were never warned before a
subscription lapsed. This sweep publishes that event for every active
subscription whose ``current_period_end`` falls inside the warning window. The
email matrix's wildcard bus subscriber (registered in platform_runtime AppConfig)
turns each published event into the tenant-admin reminder email.

Dedup is migration-free: ``publish_event`` writes a ``PlatformEventLog`` row
keyed by our per-period ``idempotency_key``; that row IS the "already reminded"
record, so a daily sweep never double-sends for the same period.

Configurable via ``BILLING_RENEWAL_REMINDER_WARNING_DAYS`` (default 7).
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

_EVENT = "tenant.subscription.expiring_soon"
_TRIAL_EVENT = "tenant.subscription.trial_ending"
_DEFAULT_WARNING_DAYS = 7
_DEFAULT_LIMIT = 500  # magic-number-allow: default-sweep-batch-cap


def _warning_days() -> int:
    try:
        return max(
            1,
            int(getattr(settings, "BILLING_RENEWAL_REMINDER_WARNING_DAYS", _DEFAULT_WARNING_DAYS)),
        )
    except (TypeError, ValueError):
        return _DEFAULT_WARNING_DAYS


def _already_reminded(event_type: str, idempotency_key: str) -> bool:
    """True when a reminder of this type for this exact period was already published."""
    try:
        from apps.platform_runtime.models import PlatformEventLog

        # tenant-isolation-allow: platform-event-log-dedup-ledger-not-tenant-scoped
        return PlatformEventLog.objects.filter(
            event_type=event_type, idempotency_key=idempotency_key
        ).exists()
    except Exception:  # noqa: BLE001 - a dedup-check failure must never break the sweep
        return False


def run_subscription_renewal_reminders(
    *,
    as_of=None,
    warning_days: int | None = None,
    limit: int = _DEFAULT_LIMIT,
    dry_run: bool = False,
) -> dict:
    """Publish ``tenant.subscription.expiring_soon`` for soon-to-renew subscriptions.

    Scans ACTIVE subscriptions with ``current_period_end`` in
    ``[as_of, as_of + warning_days]`` and publishes the reminder event once per
    subscription per period (deduped via PlatformEventLog). Returns a summary
    dict. Safe to call from a management command, Celery beat, or smoke;
    ``dry_run=True`` reports the would-publish shape without emitting events.
    """
    from apps.billing.models import TenantSubscription
    from apps.platform_runtime.event_bus import publish_event
    from apps.platform_runtime.reactivation_engine import (
        _portal_url_for_reactivation,
        _resolve_admin_email,
    )

    as_of = as_of or timezone.now()
    warning_days = warning_days or _warning_days()
    window_end = as_of + timedelta(days=warning_days)
    summary = {
        "dry_run": dry_run,
        "warning_days": warning_days,
        "scanned": 0,
        "published": 0,
        "skipped_no_email": 0,
        "skipped_deduped": 0,
    }

    # tenant-isolation-allow: platform-renewal-reminder-sweep-operator-wide-no-tenant-scope
    subs = (
        TenantSubscription.objects.select_related("school")
        .filter(
            status=TenantSubscription.Status.ACTIVE,
            current_period_end__gte=as_of,
            current_period_end__lte=window_end,
        )
        .order_by("current_period_end")[: max(1, int(limit))]
    )
    for sub in subs:
        summary["scanned"] += 1
        school = sub.school
        period_end = sub.current_period_end
        if school is None or period_end is None:
            continue
        key = f"expiring:{sub.pk}:{period_end:%Y-%m-%d}"
        if _already_reminded(_EVENT, key):
            summary["skipped_deduped"] += 1
            continue
        admin_email = _resolve_admin_email(school)
        if not admin_email:
            summary["skipped_no_email"] += 1
            continue
        days_until = max((period_end.date() - as_of.date()).days, 0)
        payload = {
            "school_id": str(school.pk),
            "admin_email": admin_email,
            "days_until": days_until,
            "renewal_url": _portal_url_for_reactivation(school),
        }
        if dry_run:
            summary["published"] += 1
            continue
        try:
            publish_event(
                _EVENT, payload, school_id=str(school.pk), idempotency_key=key
            )
            summary["published"] += 1
        except Exception:  # noqa: BLE001 - one bad row must not abort the whole sweep
            logger.exception("renewal_reminder_publish_failed sub=%s", sub.pk)
    return summary


def run_trial_ending_reminders(
    *,
    as_of=None,
    warning_days: int | None = None,
    limit: int = _DEFAULT_LIMIT,
    dry_run: bool = False,
) -> dict:
    """Publish ``tenant.subscription.trial_ending`` for trials about to end.

    Scans TRIALING subscriptions whose ``trial_end_date`` is in
    ``[today, today + warning_days]`` and publishes the trial-ending event once
    per subscription per trial-end date (deduped via PlatformEventLog). Same
    shape + safety as ``run_subscription_renewal_reminders``; the email matrix's
    wildcard subscriber turns each publish into the admin email.
    """
    from apps.billing.models import TenantSubscription
    from apps.platform_runtime.event_bus import publish_event
    from apps.platform_runtime.reactivation_engine import (
        _portal_url_for_reactivation,
        _resolve_admin_email,
    )

    as_of = as_of or timezone.now()
    warning_days = warning_days or _warning_days()
    today = as_of.date()
    window_end = today + timedelta(days=warning_days)
    summary = {
        "dry_run": dry_run,
        "warning_days": warning_days,
        "scanned": 0,
        "published": 0,
        "skipped_no_email": 0,
        "skipped_deduped": 0,
    }

    # tenant-isolation-allow: platform-trial-ending-reminder-sweep-operator-wide-no-tenant-scope
    subs = (
        TenantSubscription.objects.select_related("school")
        .filter(
            status=TenantSubscription.Status.TRIALING,
            trial_end_date__gte=today,
            trial_end_date__lte=window_end,
        )
        .order_by("trial_end_date")[: max(1, int(limit))]
    )
    for sub in subs:
        summary["scanned"] += 1
        school = sub.school
        trial_end = sub.trial_end_date
        if school is None or trial_end is None:
            continue
        key = f"trial-ending:{sub.pk}:{trial_end:%Y-%m-%d}"
        if _already_reminded(_TRIAL_EVENT, key):
            summary["skipped_deduped"] += 1
            continue
        admin_email = _resolve_admin_email(school)
        if not admin_email:
            summary["skipped_no_email"] += 1
            continue
        days_until = max((trial_end - today).days, 0)
        payload = {
            "school_id": str(school.pk),
            "admin_email": admin_email,
            "days_until": days_until,
            "renewal_url": _portal_url_for_reactivation(school),
        }
        if dry_run:
            summary["published"] += 1
            continue
        try:
            publish_event(
                _TRIAL_EVENT, payload, school_id=str(school.pk), idempotency_key=key
            )
            summary["published"] += 1
        except Exception:  # noqa: BLE001 - one bad row must not abort the whole sweep
            logger.exception("trial_ending_reminder_publish_failed sub=%s", sub.pk)
    return summary
