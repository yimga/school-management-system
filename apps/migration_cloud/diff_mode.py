"""Diff-mode / since-timestamp re-ingest (Tier 1 #6).

Schools migrate twice: rehearsal + real cutover, or partial + delta. Until
this module existed, a re-run re-imported everything because nothing
tracked "what changed at the source since the last bundle." Diff-mode
addresses this two ways:

    1. **Since-timestamp filter.** When ``bundle.diff_mode == 'since'`` and
       ``bundle.diff_since`` is set, the row iterator in the orchestrator
       skips rows whose ``updated_at`` / ``modified_at`` / ``last_change``
       column predates the threshold. Rows without a timestamp column fall
       through (we never silently drop data).

    2. **Last-successful-apply derivation.** :func:`recommended_diff_since`
       finds the most recent APPLIED/RECONCILED bundle for the same school +
       source system and returns its ``completed_at``. The wizard offers
       this as the default value in the diff-mode form.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any

from .models import BundleStatus, MigrationBundle

logger = logging.getLogger(__name__)


_TIMESTAMP_COLUMNS = (
    "updated_at", "modified_at", "last_change", "last_modified",
    "lastmodified", "lastupdated", "modified", "updated", "changed_at",
    "last_update", "modified_date", "updated_date",
)


def recommended_diff_since(*, school_id: int | None, source_system: str) -> _dt.datetime | None:
    """Find the timestamp of the last successful bundle for this (school, source).

    Returns None when there's no prior bundle — caller renders an empty
    field and asks the operator to specify their own.
    """
    qs = MigrationBundle.objects.filter(  # tenant-isolation-allow: optionally narrowed by school_id below
        status__in=[BundleStatus.APPLIED, BundleStatus.RECONCILED],
    )
    if school_id is not None:
        qs = qs.filter(school_id=school_id)
    candidates = qs.order_by("-completed_at")[:25]
    for prior in candidates:
        chosen = (prior.discovery_summary or {}).get("source", {}).get("chosen") or ""
        if not source_system or chosen == source_system:
            return prior.completed_at
    return None


def row_passes_diff_filter(*, row: dict[str, Any], threshold: _dt.datetime | None) -> bool:
    """True when the row is newer than ``threshold`` (or has no timestamp)."""
    if threshold is None:
        return True
    for col in _TIMESTAMP_COLUMNS:
        raw = row.get(col)
        if raw in (None, ""):
            continue
        parsed = _to_datetime(raw)
        if parsed is None:
            continue
        return parsed >= threshold
    # No recognised timestamp column — fall through to "include".
    return True


def _to_datetime(value: Any) -> _dt.datetime | None:
    if isinstance(value, _dt.datetime):
        return value
    if isinstance(value, _dt.date):
        return _dt.datetime.combine(value, _dt.time.min)
    s = str(value).strip()
    if not s:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y",
    ):
        try:
            return _dt.datetime.strptime(s[: len(fmt) + 6], fmt)
        except ValueError:
            continue
    try:
        return _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
