"""v4.00.36 Phase 3 — per-tenant usage caps + soft-warn + auto-freeze.

Closes the doc's "automated fraud suppression indices" ask. Three layers:

1. ``UsageCap`` row per ``(school, dimension)`` declares ``soft_warn_at``
   and ``hard_cap`` integers. Either field can be 0 (= no limit).
2. ``evaluate_cap(school, dimension)`` reads the current period's
   ``UsageMeter.quantity`` and returns a ``CapVerdict`` with the band:

   * ``ok`` — under soft_warn
   * ``soft_warn`` — between soft_warn and hard_cap
   * ``hard_cap`` — at or past hard_cap

3. ``enforce_cap_actions(school, dimension)`` runs the verdict and,
   under ``hard_cap``, sets ``BillingAccount.status = SUSPENDED`` and
   appends a metadata audit trail. Idempotent: a tenant already SUSPENDED
   stays SUSPENDED; auto-unfreeze must be a deliberate human action.

The verdict is exposed as a pure read for dashboards (no side effects).
The enforce action is what middleware / Celery beats call. Both are
safe to call from request paths — every error path is swallowed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date as _date_cls
from typing import Any

from django.utils import timezone

from apps.billing.models_usage_caps import UsageCap  # noqa: F401 — re-export

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CapVerdict:
    band: str  # "ok" | "soft_warn" | "hard_cap" | "no_cap"
    current: int
    soft_warn_at: int
    hard_cap: int
    dimension: str

    @property
    def is_warned(self) -> bool:
        return self.band in ("soft_warn", "hard_cap")

    @property
    def is_capped(self) -> bool:
        return self.band == "hard_cap"


def _current_period_window(grain: str, today: _date_cls) -> tuple[_date_cls, _date_cls]:
    if grain == "month":
        from calendar import monthrange

        start = today.replace(day=1)
        end = today.replace(day=monthrange(today.year, today.month)[1])
        return start, end
    return today, today


def evaluate_cap(school: Any, dimension: str) -> CapVerdict:
    """Return the current cap band for ``(school, dimension)``. Pure read."""
    zero = CapVerdict(band="no_cap", current=0, soft_warn_at=0, hard_cap=0, dimension=dimension)
    if school is None or not dimension:
        return zero
    try:
        # tenant-isolation-allow: usage-cap-scoped-via-school-fk-evaluator
        cap = UsageCap.objects.filter(school=school, dimension=dimension).first()
    except (AttributeError, RuntimeError, ValueError):
        return zero
    if cap is None:
        return zero
    grain = cap.period_grain or "day"
    today = timezone.now().date()
    start, end = _current_period_window(grain, today)
    try:
        from apps.billing.models import UsageMeter

        # tenant-isolation-allow: usage-cap-current-period-meter-scoped-via-school-fk
        rows = UsageMeter.objects.filter(
            school=school,
            metric_code=dimension,
            period_start__gte=start,
            period_end__lte=end,
        ).values_list("quantity", flat=True)
    except (ImportError, RuntimeError, AttributeError, ValueError):
        rows = []
    current = sum(int(q or 0) for q in rows)
    soft = int(cap.soft_warn_at or 0)
    hard = int(cap.hard_cap or 0)
    if hard and current >= hard:
        band = "hard_cap"
    elif soft and current >= soft:
        band = "soft_warn"
    elif soft == 0 and hard == 0:
        band = "no_cap"
    else:
        band = "ok"
    return CapVerdict(
        band=band, current=current, soft_warn_at=soft, hard_cap=hard, dimension=dimension
    )


def enforce_cap_actions(school: Any, dimension: str) -> CapVerdict:
    """Evaluate + apply side effects.

    * ``soft_warn`` → log + append metadata audit on ``BillingAccount``.
    * ``hard_cap`` → suspend ``BillingAccount`` (idempotent), log + audit.

    Returns the verdict so callers can react to the band.
    """
    verdict = evaluate_cap(school, dimension)
    if not verdict.is_warned:
        return verdict
    try:
        from apps.billing.models import BillingAccount
        from apps.billing.services import ensure_billing_account_for_school

        account, _ = ensure_billing_account_for_school(school)
    except (ImportError, RuntimeError, AttributeError, ValueError) as exc:
        logger.debug("usage cap enforce: cannot resolve billing account: %s", exc)
        return verdict

    try:
        metadata = dict(account.metadata or {})
    except (AttributeError, TypeError):
        metadata = {}
    metadata.setdefault("usage_cap_events", [])
    event_record = {
        "dimension": verdict.dimension,
        "band": verdict.band,
        "current": verdict.current,
        "soft_warn_at": verdict.soft_warn_at,
        "hard_cap": verdict.hard_cap,
        "at": timezone.now().isoformat(),
    }
    # Keep at most 50 events so metadata doesn't grow without bound.
    events = list(metadata["usage_cap_events"])[-49:] + [event_record]
    metadata["usage_cap_events"] = events
    updated_fields = ["metadata"]
    account.metadata = metadata

    if verdict.is_capped and account.status != BillingAccount.Status.SUSPENDED:
        account.status = BillingAccount.Status.SUSPENDED
        updated_fields.append("status")
        logger.warning(
            "usage cap HARD: school=%s dim=%s current=%d hard=%d -> SUSPEND",
            getattr(school, "pk", "?"),
            verdict.dimension,
            verdict.current,
            verdict.hard_cap,
        )
    else:
        logger.info(
            "usage cap SOFT: school=%s dim=%s current=%d soft=%d",
            getattr(school, "pk", "?"),
            verdict.dimension,
            verdict.current,
            verdict.soft_warn_at,
        )
    try:
        account.save(update_fields=updated_fields + ["updated_at"])
    except (AttributeError, RuntimeError, ValueError) as exc:
        logger.debug("usage cap enforce save failed: %s", exc)
    return verdict


__all__ = ["UsageCap", "CapVerdict", "evaluate_cap", "enforce_cap_actions"]
