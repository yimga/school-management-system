"""Delinquency dunning-reminder ladder (Metric 6 — Billing/PPP).

The billing lifecycle FSM (``apps.billing.services._advance_subscription_billing``)
ALREADY ages a subscription with an unpaid balance ``active → past_due →
suspended`` on configurable day-offsets (``grace_days`` / ``suspension_days``),
clears the delinquency on a payment (balance ``<= 0``), and is idempotent. What
it did NOT do was *tell the tenant*: the only past-due email in the codebase fired
from the PSP webhook bridge (``apply_processor_snapshot`` →
``tenant.payment.failed``), which needs a live external processor webhook. A
tenant whose platform-ledger balance goes unpaid for any other reason (a manual
invoice, a failed card whose webhook never arrived) therefore aged silently from
past-due to suspended with no warning.

This sweep is the missing rung: a scheduled, escalating **dunning ladder** driven
off the platform ledger (no PSP required). For every delinquent subscription
(``status in {PAST_DUE, SUSPENDED}`` with a set ``delinquent_since`` and a still
positive balance) it computes days-overdue and publishes ONE reminder for the
most-escalated stage that has not yet been sent for this delinquency episode:

    dunning_1 (day 0)  →  dunning_2  →  final_notice  →  suspended

Stage day-offsets are configurable via ``BILLING_DUNNING_REMINDER_OFFSET_DAYS``.
Recovery is automatic: the lifecycle FSM clears ``delinquent_since`` on payment,
so the next sweep sees an ``ACTIVE`` subscription and stops — and a *future*
delinquency episode gets a fresh ``delinquent_since`` date, so its idempotency
keys don't collide with the resolved episode's.

Dedup is migration-free and mirrors ``apps.billing.renewal_reminders``:
``publish_event`` writes a ``PlatformEventLog`` row keyed by our per-stage
``idempotency_key``; that row IS the "already reminded" record, so a daily sweep
(or a re-run within the same day) never double-sends the same stage. The email
matrix's wildcard subscriber turns each published ``tenant.subscription.past_due``
event into the tenant-admin reminder email.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

_EVENT = "tenant.subscription.past_due"

# Days after ``delinquent_since`` at which each reminder rung fires. The last
# rung is the "final notice"; earlier rungs are numbered ``dunning_N``. Small
# day counts — kept configurable, never hardcoded at the callsite.
_DEFAULT_OFFSET_DAYS = (0, 7, 21)
# Mirrors the lifecycle FSM defaults so reminder copy can say "suspended in N
# days" without the FSM and the reminder drifting apart.
_DEFAULT_GRACE_DAYS = 7
_DEFAULT_SUSPENSION_DAYS = 30
_DEFAULT_LIMIT = 500  # magic-number-allow: default-sweep-batch-cap


def _int_setting(name: str, default: int) -> int:
    try:
        return int(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default


def _offset_days() -> tuple[int, ...]:
    """Sorted, de-duplicated, non-negative ladder offsets (days)."""
    raw = getattr(settings, "BILLING_DUNNING_REMINDER_OFFSET_DAYS", _DEFAULT_OFFSET_DAYS)
    try:
        cleaned = sorted({max(0, int(v)) for v in raw})
    except (TypeError, ValueError):
        cleaned = list(_DEFAULT_OFFSET_DAYS)
    return tuple(cleaned) or _DEFAULT_OFFSET_DAYS


def _ladder() -> list[tuple[str, int]]:
    """Return ``[(stage_label, offset_days), ...]`` in ascending offset order."""
    offsets = _offset_days()
    last = len(offsets) - 1
    return [
        ("final_notice" if i == last else f"dunning_{i + 1}", off)
        for i, off in enumerate(offsets)
    ]


def _suspension_offset_days() -> int:
    """Days after ``delinquent_since`` at which the FSM suspends.

    ``delinquent_since`` is set to the grace boundary, so suspension lands
    ``suspension_days - grace_days`` days later (0 if misconfigured).
    """
    grace = _int_setting("BILLING_GRACE_DAYS", _DEFAULT_GRACE_DAYS)
    suspend = _int_setting("BILLING_SUSPENSION_DAYS", _DEFAULT_SUSPENSION_DAYS)
    return max(suspend - grace, 0)


def _already_reminded(idempotency_key: str) -> bool:
    """True when this exact stage was already published for this episode."""
    try:
        from apps.platform_runtime.models import PlatformEventLog

        # tenant-isolation-allow: platform-event-log-dedup-ledger-not-tenant-scoped
        return PlatformEventLog.objects.filter(
            event_type=_EVENT, idempotency_key=idempotency_key
        ).exists()
    except Exception:  # noqa: BLE001 - a dedup-check failure must never break the sweep
        return False


def _stage_key(sub_pk, delinquent_since, stage: str) -> str:
    return f"dunning:{sub_pk}:{delinquent_since:%Y-%m-%d}:{stage}"


def run_subscription_dunning_reminders(
    *,
    as_of=None,
    limit: int = _DEFAULT_LIMIT,
    dry_run: bool = False,
) -> dict:
    """Publish ``tenant.subscription.past_due`` for delinquent subscriptions.

    Scans ``PAST_DUE``/``SUSPENDED`` subscriptions whose billing account carries a
    ``delinquent_since`` anchor and a still-positive balance, and publishes the
    single most-escalated dunning stage not yet sent for the current delinquency
    episode (deduped per stage via ``PlatformEventLog``). Returns a summary dict.
    Safe to call from a management command, Celery beat, or smoke; ``dry_run=True``
    reports the would-publish shape without emitting events.
    """
    from apps.billing.models import TenantSubscription
    from apps.billing.services import platform_account_balance
    from apps.platform_runtime.event_bus import publish_event
    from apps.platform_runtime.reactivation_engine import (
        _portal_url_for_reactivation,
        _resolve_admin_email,
    )

    as_of = as_of or timezone.now()
    ladder = _ladder()
    suspend_offset = _suspension_offset_days()
    summary = {
        "dry_run": dry_run,
        "scanned": 0,
        "published": 0,
        "skipped_no_email": 0,
        "skipped_deduped": 0,
        "skipped_not_delinquent": 0,
        "by_stage": {},
    }

    delinquent_statuses = [
        TenantSubscription.Status.PAST_DUE,
        TenantSubscription.Status.SUSPENDED,
    ]
    # tenant-isolation-allow: platform-dunning-reminder-sweep-operator-wide-no-tenant-scope
    subs = (
        TenantSubscription.objects.select_related("school", "billing_account")
        .filter(
            status__in=delinquent_statuses,
            billing_account__delinquent_since__isnull=False,
        )
        .order_by("billing_account__delinquent_since")[: max(1, int(limit))]
    )

    for sub in subs:
        summary["scanned"] += 1
        school = sub.school
        account = sub.billing_account
        delinquent_since = account.delinquent_since if account else None
        if school is None or account is None or delinquent_since is None:
            summary["skipped_not_delinquent"] += 1
            continue

        # Defensive: if the balance has already cleared but the FSM has not yet
        # re-run to restore the subscription, don't dun a paid-up tenant.
        balance = platform_account_balance(account)
        if balance <= 0:
            summary["skipped_not_delinquent"] += 1
            continue

        is_suspended = sub.status == TenantSubscription.Status.SUSPENDED
        days_overdue = max((as_of.date() - delinquent_since.date()).days, 0)

        # Once suspended, only the terminal notice fires — never backfill an
        # earlier reminder rung after access is already cut.
        if is_suspended:
            candidates = ["suspended"]
        else:
            candidates = [label for (label, off) in ladder if days_overdue >= off]

        # Fire the most-escalated (last) candidate not yet sent this episode.
        target_stage = None
        target_key = None
        for label in reversed(candidates):
            key = _stage_key(sub.pk, delinquent_since, label)
            if not _already_reminded(key):
                target_stage = label
                target_key = key
                break

        if target_stage is None:
            summary["skipped_deduped"] += 1
            continue

        admin_email = _resolve_admin_email(school)
        if not admin_email:
            summary["skipped_no_email"] += 1
            continue

        is_final = target_stage == "final_notice"
        will_suspend_in_days = (
            0 if is_suspended else max(suspend_offset - days_overdue, 0)
        )
        # amount_due is Decimal — quantize to money precision for display, never
        # via float() (Decimal→float silently corrupts ledger sums).
        raw_due = balance if isinstance(balance, Decimal) else Decimal(str(balance))
        amount_due = raw_due.quantize(Decimal("0.01"))
        payload = {
            "school_id": str(school.pk),
            "school_name": getattr(school, "name", "") or getattr(school, "slug", ""),
            "admin_email": admin_email,
            "dunning_stage": target_stage,
            "is_final": is_final,
            "is_suspended": is_suspended,
            "days_overdue": days_overdue,
            "will_suspend_in_days": will_suspend_in_days,
            "amount_due": str(amount_due),
            "currency_code": account.currency_code,
            "renewal_url": _portal_url_for_reactivation(school),
        }

        summary["by_stage"][target_stage] = summary["by_stage"].get(target_stage, 0) + 1
        if dry_run:
            summary["published"] += 1
            continue
        try:
            publish_event(
                _EVENT, payload, school_id=str(school.pk), idempotency_key=target_key
            )
            summary["published"] += 1
        except Exception:  # noqa: BLE001 - one bad row must not abort the whole sweep
            logger.exception("dunning_reminder_publish_failed sub=%s", sub.pk)

    return summary
