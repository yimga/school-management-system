"""v4.00.55 — LMS Celery beat schedule SOT.

Bundles the three sweeps shipped in v4.00.53 (token refresh), v4.00.54
(token rotation, audit retention) into a single SOT dict so operators
can wire them with one import rather than maintaining 3 separate
``CELERY_BEAT_SCHEDULE`` entries in ``config/settings.py``.

Usage from ``config/celery.py`` (or any startup site that holds the
Celery app):

  >>> from apps.integrations_marketplace.beat_schedule import (
  ...     LMS_BEAT_SCHEDULE,
  ...     install_lms_beat_schedule,
  ... )
  >>> install_lms_beat_schedule(app)

The installer is **idempotent** — it preserves any pre-existing key in
``app.conf.beat_schedule`` so this module never silently overwrites a
beat entry an operator wrote by hand. It also respects per-entry
disable env vars so each sweep can be staged independently.

Per-entry env-var disable flags
-------------------------------

* ``RMC_LMS_TOKEN_REFRESH_BEAT_DISABLED=1`` — skip the hourly refresh sweep.
* ``RMC_LMS_TOKEN_ROTATION_BEAT_DISABLED=1`` — skip the daily 03:30 UTC rotation sweep.
* ``RMC_LMS_AUDIT_RETENTION_BEAT_DISABLED=1`` — skip the weekly Sun 04:00 UTC purge.

The disabled-flag check happens at install time so changes require a
worker restart — by design, since beat config is not hot-reloadable.

Schedule design
---------------

* ``integrations-refresh-lms-tokens`` — every hour (3600s) with
  ``expires=3300``. Matches v4.00.53's 24h refresh window: tokens get
  swept ~1.4 times before they actually expire, so even with one
  hourly miss the inline middleware still has 60s warmup.
* ``integrations-rotate-lms-tokens`` — daily 03:30 UTC. Catches the
  cliff cases the hourly refresh can't fix. Time is chosen to avoid
  the 03:00 / 04:00 cluster other beats already use.
* ``integrations-purge-lms-audit-rows`` — weekly Sunday 04:00 UTC.
  The audit table grows slowly so daily purge is overkill; weekly
  keeps the table bounded without thrashing.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _env_bool(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _build_schedule() -> dict[str, dict[str, Any]]:
    """Lazily-built SOT so the celery import only happens when wiring.

    Returns the schedule dict with crontab/floats; entries the operator
    has flagged as disabled are omitted.
    """
    try:
        from celery.schedules import crontab  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.warning("beat_schedule: celery not importable — schedule empty: %s", exc)
        return {}

    schedule: dict[str, dict[str, Any]] = {}

    if not _env_bool("RMC_LMS_TOKEN_REFRESH_BEAT_DISABLED"):
        schedule["integrations-refresh-lms-tokens"] = {
            "task": "integrations_marketplace.refresh_due_lms_tokens",
            "schedule": 3600.0,
            "options": {"expires": 3300},
        }

    if not _env_bool("RMC_LMS_TOKEN_ROTATION_BEAT_DISABLED"):
        schedule["integrations-rotate-lms-tokens"] = {
            "task": "integrations_marketplace.rotate_due_lms_tokens",
            "schedule": crontab(hour=3, minute=30),
            "options": {"expires": 3600},
        }

    if not _env_bool("RMC_LMS_AUDIT_RETENTION_BEAT_DISABLED"):
        schedule["integrations-purge-lms-audit-rows"] = {
            "task": "integrations_marketplace.purge_due_lms_audit_rows",
            "schedule": crontab(hour=4, minute=0, day_of_week="sun"),
            "options": {"expires": 7200},
        }

    # v4.00.59 — reactive OAuth health beat: catch tokens that fully expired
    # despite the hourly proactive refresh. Default cadence 15 minutes; each
    # outcome emits an LMSPushGradeAudit row tagged ``course_id="_health_check"``
    # so /super/migration/lms/diagnostics/ surfaces the result in the 24h rollup.
    if not _env_bool("RMC_LMS_OAUTH_HEALTH_BEAT_DISABLED"):
        schedule["integrations-lms-oauth-health"] = {
            "task": "integrations_marketplace.auto_refresh_expired_lms_tokens",
            "schedule": 900.0,
            "options": {"expires": 600},
        }

    # v4.00.60 — auto-prune revoked OAuth grants. Walks expired rows whose
    # refresh attempt classifies as ``refresh_revoked`` (per v4.00.54 hints
    # + 400/401/403) and clears BOTH access_token AND refresh_token so the
    # health/rotation beats don't hammer the dead grant every cycle. Daily
    # 02:30 UTC to keep the window away from the 03:00 / 03:30 / 04:00 cluster.
    if not _env_bool("RMC_LMS_OAUTH_AUTO_PRUNE_BEAT_DISABLED"):
        schedule["integrations-lms-oauth-auto-prune"] = {
            "task": "integrations_marketplace.auto_prune_revoked_lms_tokens",
            "schedule": crontab(hour=2, minute=30),
            "options": {"expires": 3600},
        }

    # v4.00.63 — LMSDiagActionAudit retention sweep (7y FERPA cutoff).
    # Weekly Sun 04:30 UTC, just after the v4.00.55 audit-retention purge
    # at 04:00. Sweep is dry-run-capable via env so operators can stage
    # rollout; respects RMC_LMS_DIAG_ACTION_RETENTION_YEARS=0 for forever-retain.
    if not _env_bool("RMC_LMS_DIAG_ACTION_RETENTION_BEAT_DISABLED"):
        schedule["integrations-purge-lms-diag-action-rows"] = {
            "task": "integrations_marketplace.purge_due_lms_diag_action_rows",
            "schedule": crontab(hour=4, minute=30, day_of_week="sun"),
            "options": {"expires": 7200},
        }

    return schedule


# ---------------------------------------------------------------------------
# Importable SOT — also computed lazily so a celery-less runtime
# (tests, ad-hoc scripts) doesn't fail at import time.
# ---------------------------------------------------------------------------
def get_lms_beat_schedule() -> dict[str, dict[str, Any]]:
    """Return the LMS beat schedule SOT dict (lazy, respects env disables)."""
    return _build_schedule()


# Backwards-compat alias for operators who prefer module-level constant.
LMS_BEAT_SCHEDULE = get_lms_beat_schedule()


def install_lms_beat_schedule(app, *, override: bool = False) -> dict[str, dict[str, Any]]:
    """Install LMS beat entries on a Celery ``app.conf.beat_schedule``.

    Idempotent: existing keys in ``app.conf.beat_schedule`` are preserved
    UNLESS ``override=True`` is passed. Returns the dict of entries
    that were actually installed (useful for tests + audit logging).

    Safe to call at celery app construction time OR later — Celery beat
    reads ``conf.beat_schedule`` lazily on each scheduler tick.
    """
    if app is None or not hasattr(app, "conf"):
        logger.warning("beat_schedule: install called with invalid app=%r", app)
        return {}

    current = dict(getattr(app.conf, "beat_schedule", {}) or {})
    schedule = get_lms_beat_schedule()
    installed: dict[str, dict[str, Any]] = {}

    for key, entry in schedule.items():
        if key in current and not override:
            logger.debug("beat_schedule: %s already present — preserving operator config", key)
            continue
        current[key] = entry
        installed[key] = entry

    app.conf.beat_schedule = current
    logger.info(
        "beat_schedule: installed %d LMS entries (%s)",
        len(installed), ", ".join(installed.keys()) or "none",
    )
    return installed
