"""v4.00.54 — LMS push-grade audit retention sweep (FERPA 7-year cutoff).

v4.00.55 — Adds export-before-purge: writes a JSONL snapshot of the
about-to-be-purged rows to ``RMC_LMS_AUDIT_RETENTION_EXPORT_DIR``
BEFORE the bulk-delete, so operators retain a forensic record of what
left the live table. The export is opt-in (no default directory) so
the v4.00.54 behavior is preserved when the env var is unset.

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
* ``RMC_LMS_AUDIT_RETENTION_EXPORT_DIR`` — v4.00.55. When set, the
  sweep writes a JSONL snapshot of the about-to-be-purged rows to
  ``<dir>/lms_audit_purge_<utc_iso>.jsonl`` BEFORE the bulk-delete.
  The file lands with restrictive perms (0o600 / write-for-owner-only
  on POSIX; Windows ACL falls back to filesystem default since chmod
  is largely advisory there). Sweep aborts before any deletion if the
  export write fails so no data is silently lost.
* ``RMC_LMS_AUDIT_RETENTION_EXPORT_MAX_ROWS`` — v4.00.55. Defaults to
  100_000. If the about-to-be-purged batch is larger than this, the
  sweep refuses to proceed and surfaces ``error="export_batch_oversized"``
  so the operator can raise the cap or shrink the cutoff explicitly.

Pure-Python sweep:

  ``sweep_lms_audit_retention(*, years=7, now=None, dry_run=False,
  export_dir=None, export_max_rows=None) -> dict``

Celery wrapper (registered when celery is importable):

  ``apps.integrations_marketplace.purge_due_lms_audit_rows``

Failures are bounded — the sweep itself NEVER raises.
"""
from __future__ import annotations

import json as _json
import logging
import os
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_YEARS = 7
DEFAULT_EXPORT_MAX_ROWS = 100_000
_DAYS_PER_YEAR = 365  # leap-year drift acceptable for a 7-year cutoff


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name) or ""
    try:
        return int(raw) if raw else default
    except (ValueError, TypeError):
        return default


def _env_bool(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _row_to_export_dict(row) -> dict[str, Any]:
    """Serialize an LMSPushGradeAudit row to JSONL-safe shape (PII-safe by design)."""
    return {
        "id": row.pk,
        "school_id": str(row.school_id) if row.school_id else "",
        "provider": row.provider,
        "course_id": row.course_id,
        "assignment_id": row.assignment_id,
        "user_hash": row.user_hash,
        "score_text": row.score_text,
        "ok": row.ok,
        "status_code": row.status_code,
        "detail": row.detail,
        "actor_user_id": row.actor_user_id,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def _write_export(
    *, export_dir: str, rows: Iterable[Any], cutoff_iso: str,
) -> tuple[str, int] | tuple[None, str]:
    """Write a JSONL snapshot. Returns ``(filepath, count)`` on success or
    ``(None, error_reason)`` on failure."""
    try:
        directory = Path(export_dir).expanduser()
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return None, f"export_dir_unwritable: {exc}"

    # Filename uses the cutoff timestamp so multiple sweeps on the same
    # day don't collide silently (and the operator can audit which
    # cutoff produced which file).
    safe_ts = cutoff_iso.replace(":", "-").replace("+", "p")
    filename = f"lms_audit_purge_{safe_ts}.jsonl"
    filepath = directory / filename
    written = 0
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            for row in rows:
                line = _json.dumps(_row_to_export_dict(row), ensure_ascii=False, sort_keys=True)
                f.write(line)
                f.write("\n")
                written += 1
    except OSError as exc:
        return None, f"export_write_failed: {exc}"

    try:
        os.chmod(filepath, 0o600)
    except OSError:
        # Windows often returns EPERM on chmod; ignore — filesystem ACLs
        # govern access there. POSIX restrictive perm is the load-bearing case.
        pass

    return str(filepath), written


def sweep_lms_audit_retention(
    *,
    years: int | None = None,
    now=None,
    dry_run: bool | None = None,
    export_dir: str | None = None,
    export_max_rows: int | None = None,
) -> dict[str, Any]:
    """Delete (or count, in dry-run) ``LMSPushGradeAudit`` rows older
    than ``years`` years from now.

    When ``export_dir`` (or ``RMC_LMS_AUDIT_RETENTION_EXPORT_DIR``) is
    set AND ``dry_run`` is False AND there are rows to purge, the
    sweep first writes a JSONL snapshot of the rows to the directory.
    If the export write fails the sweep aborts BEFORE the bulk-delete
    so no data is silently lost.

    Returns:
        ``{"considered": N, "purged": K, "cutoff_iso": "...", "dry_run": bool,
        "retention_years": int, "exported": bool, "export_path": str,
        "export_rows": int}``  — audit-shape. Never raises.
    """
    from django.utils import timezone as _tz

    if years is None:
        years = _env_int("RMC_LMS_AUDIT_RETENTION_YEARS", DEFAULT_RETENTION_YEARS)
    if dry_run is None:
        dry_run = _env_bool("RMC_LMS_AUDIT_RETENTION_DRY_RUN")
    if export_dir is None:
        export_dir = (os.environ.get("RMC_LMS_AUDIT_RETENTION_EXPORT_DIR") or "").strip() or None
    if export_max_rows is None:
        export_max_rows = _env_int("RMC_LMS_AUDIT_RETENTION_EXPORT_MAX_ROWS", DEFAULT_EXPORT_MAX_ROWS)

    if years <= 0:
        # 0 = retain forever per operator config; no-op.
        return {
            "considered": 0,
            "purged": 0,
            "cutoff_iso": "",
            "dry_run": dry_run,
            "retention_years": years,
            "exported": False,
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
            "exported": False,
            "error": str(exc),
        }

    qs = LMSPushGradeAudit.objects.filter(  # tenant-isolation-allow: lms-audit-retention-platform-scope-celery-beat
        created_at__lt=cutoff,
    )
    considered = qs.count()
    purged = 0
    exported = False
    export_path = ""
    export_rows = 0

    # Export-before-purge contract (v4.00.55): write JSONL snapshot first.
    if not dry_run and considered and export_dir:
        if considered > export_max_rows:
            return {
                "considered": considered,
                "purged": 0,
                "cutoff_iso": cutoff.isoformat(),
                "dry_run": dry_run,
                "retention_years": years,
                "exported": False,
                "error": "export_batch_oversized",
                "export_max_rows": export_max_rows,
            }
        path_or_none, written_or_err = _write_export(
            export_dir=export_dir,
            rows=qs.iterator(chunk_size=1000),  # tenant-isolation-allow: lms-audit-retention-platform-scope-stream-purge-batch
            cutoff_iso=cutoff.isoformat(),
        )
        if path_or_none is None:
            return {
                "considered": considered,
                "purged": 0,
                "cutoff_iso": cutoff.isoformat(),
                "dry_run": dry_run,
                "retention_years": years,
                "exported": False,
                "error": str(written_or_err),
            }
        exported = True
        export_path = path_or_none
        export_rows = int(written_or_err)

    if not dry_run and considered:
        try:
            deleted, _ = qs.delete()  # tenant-isolation-allow: lms-audit-retention-platform-scope-bulk-delete-by-cutoff
            purged = int(deleted)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "lms_audit_retention: delete failed cutoff=%s considered=%s exported=%s: %s",
                cutoff.isoformat(), considered, exported, exc,
            )
            return {
                "considered": considered,
                "purged": 0,
                "cutoff_iso": cutoff.isoformat(),
                "dry_run": dry_run,
                "retention_years": years,
                "exported": exported,
                "export_path": export_path,
                "export_rows": export_rows,
                "error": str(exc),
            }

    return {
        "considered": considered,
        "purged": purged,
        "cutoff_iso": cutoff.isoformat(),
        "dry_run": dry_run,
        "retention_years": years,
        "exported": exported,
        "export_path": export_path,
        "export_rows": export_rows,
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
