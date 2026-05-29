"""Wave C — G2: usage-metering dimensions + writer helpers.

The platform already has a ``UsageMeter`` model in ``apps.billing.models``
keyed by ``(billing_account, metric_code, period_start, period_end)`` —
designed for monthly billing periods. This module:

* declares the **canonical dimension enum** so dimensions are a typed
  vocabulary, not free-form strings;
* exposes **writer helpers** that map each dimension into the existing
  ``UsageMeter`` table with day-grain (`period_start == period_end ==
  utc_day`), so daily rollups land alongside the monthly billing rollups
  in a single table;
* never declares a new ORM model — no second ``UsageMeter`` table.

Public surface (see ``apps.billing.usage_report`` for the read side):

    USAGE_DIMENSIONS / USAGE_DIMENSION_CODES — enum
    record(school, dimension, *, delta=1, day=None, metadata=None) — increment
    snapshot(school, *, day=None) — full daily row map for a school
"""

from __future__ import annotations

from datetime import date as _date
from typing import Any

from django.db import transaction
from django.db.models import F
from django.utils import timezone


USAGE_DIMENSIONS: tuple[tuple[str, str], ...] = (
    ("storage_bytes", "Storage (bytes)"),
    ("db_sessions", "DB sessions"),
    ("api_calls", "API calls"),
    ("ai_tokens", "AI tokens"),
    ("ai_invocations", "AI invocations"),
    ("sms_count", "SMS messages"),
    ("marketplace_installs", "Marketplace installs"),
)
USAGE_DIMENSION_CODES: frozenset[str] = frozenset(code for code, _ in USAGE_DIMENSIONS)


def _today() -> _date:
    return timezone.now().date()


@transaction.atomic
def record(school: Any, dimension: str, *, delta: int = 1, day: _date | None = None,
           metadata: dict | None = None) -> None:
    """Increment ``UsageMeter.quantity`` for ``(school, dimension, day)``.

    Silently returns when ``school`` is None or ``dimension`` is unknown —
    metering must never raise into a request path. The single ``UsageMeter``
    row is keyed by ``period_start == period_end == day`` so day-grain
    rollups coexist with the monthly billing rollups already in the table.
    """
    if school is None or dimension not in USAGE_DIMENSION_CODES:
        return
    if not delta:
        return
    target_day = day or _today()
    try:
        from apps.billing.models import UsageMeter
        from apps.billing.services import ensure_billing_account_for_school
    except (ImportError, RuntimeError):
        return

    try:
        account, _ = ensure_billing_account_for_school(school)
    except (AttributeError, RuntimeError, ValueError):
        return

    obj, created = UsageMeter.objects.get_or_create(
        billing_account=account,
        school=school,
        metric_code=dimension,
        period_start=target_day,
        period_end=target_day,
        defaults={"quantity": max(0, int(delta)), "metadata": metadata or {}},
    )
    if not created:
        # tenant-isolation-allow: pk lookup is globally unique; obj was just fetched via get_or_create with school=school above
        UsageMeter.objects.filter(pk=obj.pk).update(quantity=F("quantity") + int(delta))


def snapshot(school: Any, *, day: _date | None = None) -> dict[str, int]:
    """Return ``{dimension: quantity}`` for the given UTC day."""
    if school is None:
        return {code: 0 for code in USAGE_DIMENSION_CODES}
    target_day = day or _today()
    try:
        from apps.billing.models import UsageMeter

        rows = UsageMeter.objects.filter(
            school=school,
            period_start=target_day,
            period_end=target_day,
            metric_code__in=USAGE_DIMENSION_CODES,
        ).values_list("metric_code", "quantity")
    except (ImportError, RuntimeError):
        return {code: 0 for code in USAGE_DIMENSION_CODES}
    out = {code: 0 for code in USAGE_DIMENSION_CODES}
    for code, qty in rows:
        out[code] = int(qty or 0)
    return out


__all__ = [
    "USAGE_DIMENSIONS",
    "USAGE_DIMENSION_CODES",
    "record",
    "snapshot",
]
