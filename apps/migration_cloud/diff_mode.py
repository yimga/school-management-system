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
    # OneRoster v1.2 stamps every row with camelCase ``dateLastModified`` (audit
    # D-3). It arrives unmapped (``_unmapped.dateLastModified``) since the ontology
    # has no canonical updated_at, so recognising it here — and its snake variant
    # — is what turns a OneRoster ``diff_mode="since"`` re-ingest into a real delta.
    "datelastmodified", "date_last_modified",
)


def recommended_diff_since(*, school_id: int | None, source_system: str) -> _dt.datetime | None:
    """Find the timestamp of the last successful bundle for this (school, source).

    Returns None when there's no prior bundle — caller renders an empty
    field and asks the operator to specify their own. A missing ``school_id``
    also returns None: it must NEVER fall back to another tenant's most-recent
    bundle, which would seed this wizard with a cross-tenant baseline timestamp
    (and read another tenant's ``discovery_summary``).
    See docs/MIGRATION_CLOUD_AUDIT_2026_07_24.md (D-8).
    """
    if school_id is None:
        return None
    qs = MigrationBundle.objects.filter(
        school_id=school_id,
        status__in=[BundleStatus.APPLIED, BundleStatus.RECONCILED],
    )
    candidates = qs.order_by("-completed_at")[:25]
    for prior in candidates:
        chosen = (prior.discovery_summary or {}).get("source", {}).get("chosen") or ""
        if not source_system or chosen == source_system:
            return prior.completed_at
    return None


def _extract_row_timestamp(row: dict[str, Any]) -> _dt.datetime | None:
    """Find a usable modified-timestamp on a (possibly transformed) canonical row.

    The row reaching the diff filter is the TRANSFORMED canonical row from
    ``orchestrator._transform_row``: every source column with no canonical
    mapping is preserved under a ``_unmapped.<source_col>`` key (the ontology has
    no canonical ``updated_at``, so a vendor's ``LastModified`` / ``updated_at``
    ALWAYS arrives unmapped). Match ``_TIMESTAMP_COLUMNS`` against the row keys
    case-insensitively, stripping a leading ``_unmapped.`` prefix, in priority
    order. The old bare-key-only lookup never matched a real row — so every
    ``since`` delta run silently re-imported the entire source.
    See docs/MIGRATION_CLOUD_AUDIT_2026_07_24.md (BLOCKER 7).
    """
    _PREFIX = "_unmapped."
    normalized: dict[str, Any] = {}
    for key, val in row.items():
        if val in (None, ""):
            continue
        norm = key[len(_PREFIX):] if key.startswith(_PREFIX) else key
        normalized.setdefault(str(norm).strip().lower(), val)
    for col in _TIMESTAMP_COLUMNS:
        if col in normalized:
            parsed = _to_datetime(normalized[col])
            if parsed is not None:
                return parsed
    return None


def row_passes_diff_filter(*, row: dict[str, Any], threshold: _dt.datetime | None) -> bool:
    """True when the row is newer than ``threshold`` (or has no timestamp)."""
    if threshold is None:
        return True
    parsed = _extract_row_timestamp(row)
    if parsed is None:
        # No recognised timestamp column — include (never silently drop data).
        return True
    try:
        return parsed >= threshold
    except TypeError:
        # Mixed naive/aware datetimes — normalize both to naive UTC to compare.
        p = parsed.astimezone(_dt.timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
        t = threshold.astimezone(_dt.timezone.utc).replace(tzinfo=None) if threshold.tzinfo else threshold
        return p >= t


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
