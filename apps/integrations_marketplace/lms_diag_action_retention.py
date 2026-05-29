"""v4.00.63 — LMSDiagActionAudit retention sweep (7y FERPA default).

Companion to v4.00.54 ``lms_audit_retention.py`` (which handles the
``LMSPushGradeAudit`` table). This sweep targets the v4.00.62-introduced
``LMSDiagActionAudit`` table — operator force-refresh / force-rotate
clicks on the diagnostics dashboard.

The table carries no raw PII (``actor_hash`` is SHA-256[:12] of the
operator's username, never the raw username), so the privacy floor is
already strong. The retention sweep enforces the platform's
"don't grow audit tables without bound" default.

Operator-overridable env vars
-----------------------------

* ``RMC_LMS_DIAG_ACTION_RETENTION_YEARS`` — default 7. Set to 0 to retain
  forever (operators whose retention counsel has approved permanent
  retention).
* ``RMC_LMS_DIAG_ACTION_RETENTION_DRY_RUN`` — set to ``1`` to count only,
  never delete. Useful for staged rollout / counsel review.
* ``RMC_LMS_DIAG_ACTION_RETENTION_BEAT_DISABLED`` — set to ``1`` to skip
  the weekly Celery beat entry.

Pure-Python sweep:

  ``sweep_lms_diag_action_retention(*, years=7, now=None, dry_run=False)
    -> dict``

Celery wrapper (registered when celery is importable):

  ``apps.integrations_marketplace.purge_due_lms_diag_action_rows``

Failures are bounded — the sweep itself NEVER raises.
"""
from __future__ import annotations

import logging
import os
from datetime import timedelta
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_YEARS = 7


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name) or ""
    try:
        return int(raw) if raw else default
    except (ValueError, TypeError):
        return default


def _env_bool(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def sweep_lms_diag_action_retention(
    *,
    years: int | None = None,
    now=None,
    dry_run: bool | None = None,
) -> dict[str, Any]:
    """Delete LMSDiagActionAudit rows older than the retention cutoff.

    Returns:
        ``{"considered": N, "cutoff_iso": "...", "deleted": K,
        "dry_run": bool, "years": Y}`` — audit shape.

    ``years=0`` short-circuits with ``{"deleted": 0, "skipped": "retain_forever"}``.
    NEVER raises.
    """
    from django.utils import timezone as _tz

    if years is None:
        years = _env_int("RMC_LMS_DIAG_ACTION_RETENTION_YEARS", DEFAULT_YEARS)
    if dry_run is None:
        dry_run = _env_bool("RMC_LMS_DIAG_ACTION_RETENTION_DRY_RUN")
    now = now or _tz.now()

    if years <= 0:
        return {
            "considered": 0,
            "deleted": 0,
            "skipped": "retain_forever",
            "dry_run": bool(dry_run),
            "years": int(years),
        }

    # 365.25 days/year accounts for leap years over the 7y window.
    cutoff = now - timedelta(days=int(round(years * 365.25)))

    try:
        from apps.integrations_marketplace.models import LMSDiagActionAudit
    except Exception as exc:  # noqa: BLE001
        logger.debug("lms_diag_action_retention: model unavailable: %s", exc)
        return {
            "considered": 0,
            "deleted": 0,
            "dry_run": bool(dry_run),
            "years": int(years),
            "error": str(exc),
        }

    try:
        qs = LMSDiagActionAudit.objects.filter(  # tenant-isolation-allow: lms-diag-action-retention-platform-scope-celery-beat
            created_at__lt=cutoff,
        )
        considered = qs.count()
    except Exception as exc:  # noqa: BLE001
        logger.warning("lms_diag_action_retention: count failed: %s", exc)
        return {
            "considered": 0,
            "deleted": 0,
            "dry_run": bool(dry_run),
            "years": int(years),
            "error": str(exc),
        }

    if dry_run or considered == 0:
        return {
            "considered": considered,
            "cutoff_iso": cutoff.isoformat(),
            "deleted": 0,
            "dry_run": bool(dry_run),
            "years": int(years),
        }

    try:
        deleted_info = qs.delete()
        deleted = int(deleted_info[0] if isinstance(deleted_info, tuple) else considered)
    except Exception as exc:  # noqa: BLE001
        logger.warning("lms_diag_action_retention: delete failed: %s", exc)
        return {
            "considered": considered,
            "cutoff_iso": cutoff.isoformat(),
            "deleted": 0,
            "dry_run": False,
            "years": int(years),
            "error": str(exc),
        }

    logger.info(
        "lms_diag_action_retention: deleted=%d cutoff=%s years=%d",
        deleted, cutoff.isoformat(), years,
    )
    return {
        "considered": considered,
        "cutoff_iso": cutoff.isoformat(),
        "deleted": deleted,
        "dry_run": False,
        "years": int(years),
    }


# ---------------------------------------------------------------------------
# Celery wrapper (registered lazily when celery is importable).
# ---------------------------------------------------------------------------
try:
    from celery import shared_task  # type: ignore

    @shared_task(name="integrations_marketplace.purge_due_lms_diag_action_rows")
    def purge_due_lms_diag_action_rows() -> dict[str, Any]:
        """Celery beat entry — runs ``sweep_lms_diag_action_retention`` w/ defaults."""
        return sweep_lms_diag_action_retention()
except Exception:  # pragma: no cover - celery not installed in some environments
    purge_due_lms_diag_action_rows = None  # type: ignore[assignment]
