"""Pre-rollover backup/export gate (M29 / EOY gap #3).

Year-end rollover is *destructive*: it opens a new enrollment for every active
student in the target year, closes the source-year enrollment, can graduate
students to ALUMNI, and can lock the source year. If the operator got the
source/target years wrong, or a promotion mapping is bad, the cohort has already
been moved before the mistake is noticed. The safety net is the M28 tenant DR
snapshot — a signed, encrypted, immutable full-state export of the tenant.

This module refuses to start a rollover apply unless EITHER

* a recent M28 snapshot exists for the school (``apps.lifecycle`` wrote a
  :class:`apps.lifecycle.models_dr_snapshot.TenantImmutableSnapshot` row within
  the configured window — the same row
  :func:`apps.lifecycle.tenant_dr_snapshot.capture_daily_snapshot` persists and
  the daily ``lifecycle.capture_tenant_immutable_snapshots_daily`` task drives),
  OR
* the operator explicitly overrides (an "I understand there is no backup"
  acknowledgement).

The M28 snapshot is a *whole-tenant* artifact (school FK + ``snapshot_date`` +
``created_at``); it is NOT scoped to a single academic year, so the gate keys on
``school`` + recency only. ``source_year`` is accepted for the audit line and to
keep the signature future-proof if year-scoped exports ever land.

Read-only against the M28 machinery: this module never writes a snapshot itself
(:func:`create_pre_rollover_backup` simply delegates to the existing capture
service).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

logger = logging.getLogger(__name__)

# How fresh an M28 snapshot must be to satisfy the gate. Year-end rollover is a
# once-a-year event, so a week-old backup is a sensible default; tune per-deploy
# via the setting without a code change.
DEFAULT_BACKUP_MAX_AGE_DAYS = 7

# The exact refusal message, reused by both apply paths and asserted by tests.
BACKUP_REQUIRED_MESSAGE = (
    "A data backup/export must be created before rollover — create one "
    "(use “Back up now” / the tenant DR snapshot flow) or explicitly "
    "override by acknowledging that no backup exists."
)


def _max_age_days() -> int:
    """Backup freshness window in days (setting-overridable, safe default)."""
    try:
        return int(
            getattr(
                settings,
                "RMC_PRE_ROLLOVER_BACKUP_MAX_AGE_DAYS",
                DEFAULT_BACKUP_MAX_AGE_DAYS,
            )
        )
    except (TypeError, ValueError):
        return DEFAULT_BACKUP_MAX_AGE_DAYS


def recent_backup_exists(school, *, within_days: int | None = None) -> bool:
    """True when an M28 tenant DR snapshot exists for ``school`` in the window.

    Returns ``False`` for a missing school rather than raising, so the caller
    (the gate) can turn "cannot verify a backup" into a fail-closed refusal.
    """
    if school is None or getattr(school, "pk", None) is None:
        return False
    # Imported lazily so this helper module stays importable in CI lanes that
    # do not load the lifecycle app, and so a circular import can never form.
    from apps.lifecycle.models_dr_snapshot import TenantImmutableSnapshot

    days = within_days if within_days is not None else _max_age_days()
    cutoff = timezone.now() - timedelta(days=days)
    return TenantImmutableSnapshot.objects.filter(
        school=school, created_at__gte=cutoff
    ).exists()


def require_pre_rollover_backup(
    school, source_year, *, override: bool = False, created_by=None
) -> str:
    """Gate a rollover apply on a recent backup OR an explicit override.

    Raises :class:`django.core.exceptions.ValidationError` when neither a recent
    M28 snapshot exists for ``school`` nor ``override`` is set. On success emits a
    PII-free audit line and returns the branch taken — ``"backup-present"`` or
    ``"operator-override"`` — so callers/tests can record which path was used.
    """
    school_id = getattr(school, "pk", None)
    source_year_id = getattr(source_year, "pk", None)
    actor_id = getattr(created_by, "pk", None)

    if override:
        logger.info(
            "rollover_backup_gate branch=operator-override "
            "school_id=%s source_year_id=%s actor_id=%s",
            school_id,
            source_year_id,
            actor_id,
        )
        return "operator-override"

    if recent_backup_exists(school):
        logger.info(
            "rollover_backup_gate branch=backup-present "
            "school_id=%s source_year_id=%s",
            school_id,
            source_year_id,
        )
        return "backup-present"

    logger.warning(
        "rollover_backup_gate branch=refused-no-backup "
        "school_id=%s source_year_id=%s actor_id=%s",
        school_id,
        source_year_id,
        actor_id,
    )
    raise ValidationError(BACKUP_REQUIRED_MESSAGE)


def create_pre_rollover_backup(school) -> dict[str, Any]:
    """"Back up now" affordance — trigger the M28 daily snapshot for ``school``.

    Delegates to the existing capture service; this module adds no new crypto or
    storage. Returns the capture service's result dict (snapshot id, digest, …).
    """
    from apps.lifecycle.tenant_dr_snapshot import capture_daily_snapshot

    result = capture_daily_snapshot(school)
    logger.info(
        "rollover_backup_gate action=backup-created school_id=%s snapshot_id=%s",
        getattr(school, "pk", None),
        result.get("snapshot_id"),
    )
    return result
