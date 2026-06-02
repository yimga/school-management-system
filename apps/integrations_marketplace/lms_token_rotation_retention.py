"""v4.00.76 — Token-rotation chain retention sweep.

The v3.39.x ``MigrationCloudAuditEvent`` table and the v4.00.61
``LMSPushGradeAudit`` table both accumulate token-rotation chain rows
(rows linked via ``rotated_to`` FK) over time. This module is the SOT
for the retention sweep that compacts long chains down to the active
head + previous-N tail.

Defaults:
  * Keep the current active head + 5 previous rotations (configurable
    via env ``RMC_LMS_TOKEN_ROTATION_KEEP_TAIL``).
  * Cutoff is ``years * 365`` days (env ``RMC_LMS_TOKEN_ROTATION_RETENTION_YEARS``,
    default 2).
  * ``years=0`` retain-forever short-circuit (same contract as
    ``sweep_lms_diag_action_retention``).

The actual purge logic is deferred to the calling task; this module
exposes the cutoff math + a ``compute_rotation_chain_retention_plan``
helper that returns a plan ``{cutoff_iso, keep_tail, would_purge,
would_keep}`` without writing.
"""
from __future__ import annotations

import logging
import os
from datetime import timedelta

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_YEARS = 2
DEFAULT_KEEP_TAIL = 5


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


def resolve_retention_years() -> int:
    return _env_int("RMC_LMS_TOKEN_ROTATION_RETENTION_YEARS", DEFAULT_RETENTION_YEARS)


def resolve_keep_tail() -> int:
    return _env_int("RMC_LMS_TOKEN_ROTATION_KEEP_TAIL", DEFAULT_KEEP_TAIL)


def compute_rotation_chain_retention_plan(*, years: int | None = None,
                                            keep_tail: int | None = None,
                                            now=None) -> dict:
    """Return ``{years, keep_tail, cutoff_iso, retain_forever, generated_at}``.

    No DB writes; this is read-only planning. The actual purge happens
    inside ``run_rotation_chain_retention_sweep`` which is wired into the
    Celery beat in a follow-up wave.
    """
    from django.utils import timezone as _tz

    now = now or _tz.now()
    years = years if years is not None else resolve_retention_years()
    keep_tail = keep_tail if keep_tail is not None else resolve_keep_tail()
    if years <= 0:
        return {
            "years": 0,
            "keep_tail": max(0, keep_tail),
            "cutoff_iso": "",
            "retain_forever": True,
            "generated_at": now.isoformat(),
        }
    cutoff = now - timedelta(days=int(years) * 365)  # magic-number-allow: retention-window-days
    return {
        "years": int(years),
        "keep_tail": max(0, keep_tail),
        "cutoff_iso": cutoff.isoformat(),
        "retain_forever": False,
        "generated_at": now.isoformat(),
    }


def is_chain_row_purgeable(*, created_at, position_from_head: int,
                            cutoff_dt, keep_tail: int) -> bool:
    """Return True iff the row should be purged.

    A row is purged when BOTH:
      * its ``created_at`` is before ``cutoff_dt``
      * its position-from-head is greater than ``keep_tail``
    NEVER raises — bad inputs return False (preserve the row, fail-safe).
    """
    if cutoff_dt is None:
        return False
    if created_at is None:
        return False
    try:
        if created_at >= cutoff_dt:
            return False
        if position_from_head <= keep_tail:
            return False
        return True
    except (TypeError, ValueError):
        return False
