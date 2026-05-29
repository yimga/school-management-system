"""v4.00.54 — LMS push-grade audit retention sweep (FERPA 7-year cutoff).

FERPA §99.32 and most state-level student-records statutes require K-12
schools to retain education records for 7 years after the student
graduates / leaves the school. Beyond that point, retention is at the
school's discretion and the platform default is to PURGE rows so that
operators don't accumulate unbounded PII-adjacent audit history.

The audit row carries PII-safe ``user_hash`` (SHA-256[:16]) — no raw
learner identifiers — so the privacy floor is already strong. The
retention sweep is a "do the right thing by default" layer that keeps
the audit table from growing without bound.

Operator-overridable env vars
-----------------------------

* ``RMC_LMS_AUDIT_RETENTION_YEARS`` — default 7. Set to 0 to retain
  forever (legitimate for institutions whose retention counsel has
  approved permanent retention — counsel-pending docket).
* ``RMC_LMS_AUDIT_RETENTION_DRY_RUN`` — set to ``"1"`` to count only,
  never delete. Useful for staged rollout / counsel review.

Pure-Python sweep:

  ``sweep_lms_audit_retention(*, years=7, now=None, dry_run=False) -> dict``

Celery wrapper (registered when celery is importable):

  ``apps.integrations_marketplace.purge_due_lms_audit_rows``

Failures are bounded — the sweep itself NEVER raises.
"""
from __future__ import annotations

import logging
import os
from datetime import timedelta
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_YEARS = 7
_DAYS_PER_YEAR = 365  # leap-year drift acceptable for a 7-year cutoff


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name) or ""
    try:
        return int(raw) if raw else default
    except (ValueError, TypeError):
        return default


def _env_bool(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def sweep_lms_audit_retention(
    *,
    years: int | None = None,
    now=None,
    dry_run: bool | None = None,
) -> dict[str, Any]:
    """Delete (or count, in dry-run) ``LMSPushGradeAudit`` rows older
    than ``years`` years from now.

    Returns:
        ``{"considered": N, "purged": K, "cutoff_iso": "...", "dry_run": bool,
        "retention_years": int}``  — audit-shape. Never raises.
    """
    from django.utils import timezone as _tz

    if years is None:
        years = _env_int("RMC_LMS_AUDIT_RETENTION_YEARS", DEFAULT_RETENTION_YEARS)
    if dry_run is None:
        dry_run = _env_bool("RMC_LMS_AUDIT_RETENTION_DRY_RUN")
    if years <= 0:
        # 0 = retain forever per operator config; no-op.
        return {
            "considered": 0,
            "purged": 0,
            "cutoff_iso": "",
            "dry_run": dry_run,
            "retention_years": years,
            "skipped_reason": "retention_disabled",
        }

    now = now or _tz.now()
    cutoff = now - timedelta(days=years * _DAYS_PER_YEAR)

    try:
        from apps.integrations_marketplace.models import LMSPushGradeAudit
    except Exception as exc:  # noqa: BLE001
        logger.debug("lms_audit_retention: model unavailable: %s", exc)
        return {
            "considered": 0,
            "purged": 0,
            "cutoff_iso": cutoff.isoformat(),
            "dry_run": dry_run,
            "retention_years": years,
            "error": str(exc),
        }

    qs = LMSPushGradeAudit.objects.filter(  # tenant-isolation-allow: lms-audit-retention-platform-scope-celery-beat
        created_at__lt=cutoff,
    )
    considered = qs.count()
    purged = 0

    if not dry_run and considered:
        try:
            deleted, _ = qs.delete()  # tenant-isolation-allow: lms-audit-retention-platform-scope-bulk-delete-by-cutoff
            purged = int(deleted)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "lms_audit_retention: delete failed cutoff=%s considered=%s: %s",
                cutoff.isoformat(), considered, exc,
            )
            return {
                "considered": considered,
                "purged": 0,
                "cutoff_iso": cutoff.isoformat(),
                "dry_run": dry_run,
                "retention_years": years,
                "error": str(exc),
            }

    return {
        "considered": considered,
        "purged": purged,
        "cutoff_iso": cutoff.isoformat(),
        "dry_run": dry_run,
        "retention_years": years,
    }


# ---------------------------------------------------------------------------
# Celery wrapper (registered lazily when celery is importable).
# ---------------------------------------------------------------------------
try:
    from celery import shared_task  # type: ignore

    @shared_task(name="integrations_marketplace.purge_due_lms_audit_rows")
    def purge_due_lms_audit_rows() -> dict[str, Any]:
        """Celery beat entry — runs ``sweep_lms_audit_retention`` with the
        configured retention. Return value is the audit dict (visible in
        flower/result-backend)."""
        return sweep_lms_audit_retention()
except Exception:  # pragma: no cover - celery not installed in some environments
    purge_due_lms_audit_rows = None  # type: ignore[assignment]
