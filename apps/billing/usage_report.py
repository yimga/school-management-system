"""Wave C — G2: read-side API for tenant usage.

A thin wrapper over ``UsageMeter`` (defined in ``apps.billing.models``)
that aggregates the daily rollups produced by ``models_metering.record``
into period-scoped summaries the invoicing pipeline and entitlements
gate can consume.

Public surface:

    current_period(school)          -> dict
    period(school, start, end)      -> dict
    over_quota(school, dimension)   -> tuple[bool, int, int|None]
    QUOTA_DEFAULTS                  -> {dimension: int}  (community-free tier)

Quotas live on ``Entitlement`` rows (``limit_value`` field) when set; the
``QUOTA_DEFAULTS`` map is the no-config fallback so an unconfigured tenant
still has soft-quota signalling.
"""

from __future__ import annotations

from datetime import date as _date
from datetime import timedelta
from typing import Any

from django.db.models import Sum
from django.utils import timezone

from apps.billing.models_metering import USAGE_DIMENSION_CODES


# Wave C — soft defaults for the community-free tier. Real plans override
# via the ``Entitlement.limit_value`` field at provisioning. Values picked
# to match the AWS-style "small school can run free" framing in the plan.
QUOTA_DEFAULTS: dict[str, int] = {
    "storage_bytes": 1 * 1024 * 1024 * 1024,    # magic-number-allow: 1 GiB byte conversion in named-constant dict
    "db_sessions": 50,                           # per month
    "api_calls": 100_000,                        # magic-number-allow: free-tier monthly cap in named-constant dict
    "ai_tokens": 10_000,                         # magic-number-allow: free-tier monthly cap in named-constant dict
    "marketplace_installs": 5,                   # active installs
}


def _today() -> _date:
    return timezone.now().date()


def period(school: Any, start: _date, end: _date) -> dict[str, int]:
    """Sum each dimension's ``quantity`` over the inclusive ``[start, end]`` window."""
    out = {code: 0 for code in USAGE_DIMENSION_CODES}
    if school is None or end < start:
        return out
    try:
        from apps.billing.models import UsageMeter

        rows = (
            UsageMeter.objects.filter(
                school=school,
                period_start__gte=start,
                period_end__lte=end,
                metric_code__in=USAGE_DIMENSION_CODES,
            )
            .values("metric_code")
            .annotate(total=Sum("quantity"))
        )
    except (ImportError, RuntimeError):
        return out
    for row in rows:
        out[row["metric_code"]] = int(row["total"] or 0)
    return out


def current_period(school: Any) -> dict[str, int]:
    """Month-to-date summary across all canonical dimensions."""
    today = _today()
    return period(school, today.replace(day=1), today)


def quota_for(school: Any, dimension: str) -> int | None:
    """Resolve the active quota for ``dimension``.

    Looks first at the per-school ``Entitlement.limit_value``; falls back to
    ``QUOTA_DEFAULTS``. Returns None when neither is set (i.e. unlimited).
    """
    if dimension not in USAGE_DIMENSION_CODES:
        return None
    try:
        from apps.billing.models import Entitlement

        row = (
            Entitlement.objects.filter(
                school=school,
                code=f"quota.{dimension}",
                kind=Entitlement.Kind.QUOTA,
                is_enabled=True,
            )
            .order_by("-updated_at")
            .first()
        )
        if row is not None and row.limit_value is not None:
            return int(row.limit_value)
    except (ImportError, RuntimeError, AttributeError, ValueError):
        pass
    return QUOTA_DEFAULTS.get(dimension)


def over_quota(school: Any, dimension: str) -> tuple[bool, int, int | None]:
    """Return ``(is_over, usage, quota)``.

    ``quota=None`` means unlimited (and ``is_over`` will be False). Within
    the entitlements gate, ``is_over=True`` flips to a soft warn for the
    first grace window before hard-blocking; the grace cadence lives in
    ``apps.billing.entitlements``.
    """
    usage = current_period(school).get(dimension, 0)
    q = quota_for(school, dimension)
    return (q is not None and usage > q, usage, q)


def reset_today(school: Any) -> int:
    """Clear today's rows for ``school`` across all canonical dimensions.

    Test helper; not used by production code.
    """
    if school is None:
        return 0
    try:
        from apps.billing.models import UsageMeter

        return UsageMeter.objects.filter(
            school=school,
            period_start=_today(),
            period_end=_today(),
            metric_code__in=USAGE_DIMENSION_CODES,
        ).delete()[0]
    except (ImportError, RuntimeError):
        return 0


__all__ = [
    "QUOTA_DEFAULTS",
    "current_period",
    "over_quota",
    "period",
    "quota_for",
    "reset_today",
]
