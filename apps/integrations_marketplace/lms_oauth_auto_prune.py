"""v4.00.60 — LMS connector auto-prune on ``refresh_revoked``.

Reactive companion to v4.00.59's ``lms_oauth_health``: when a refresh
attempt classifies as ``refresh_revoked`` (per the v4.00.54 rotation
classifier — ``invalid_grant``/``invalid_token``/``unauthorized_client``
in the body, or 400/401/403 status code), this sweep goes one step
further than rotation: it CLEARS BOTH ``access_token`` AND
``refresh_token`` on the row (true auto-prune) so the operator UI
surfaces the row as "OAuth grant revoked — operator action required"
instead of repeatedly hammering the upstream IdP with a dead grant.

Rationale: keeping a known-revoked ``refresh_token`` on file does NOT
recover access — the user must re-authorize via the PKCE flow at
``/portal/super/integrations/lms/<provider>/pkce/start/`` — but every
beat cycle wastes one round-trip to the upstream and inflates the
audit-row noise. Auto-prune removes the dead grant so health/rotation
beats skip these rows on subsequent cycles.

Pure-Python sweep:

  ``sweep_lms_oauth_auto_prune(now=None, max_rows=None) -> dict``

Celery wrapper (registered when celery is importable):

  ``apps.integrations_marketplace.auto_prune_revoked_lms_tokens``

NEVER raises. Honors ``RMC_LMS_OAUTH_AUTO_PRUNE_MAX_ROWS`` for batch
cap and ``RMC_LMS_OAUTH_AUTO_PRUNE_DRY_RUN=1`` for the operator dry-run
preview (classifies but does NOT mutate rows).
"""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MAX_ROWS = 500
_PRUNE_COURSE_ID = "_auto_prune"


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name) or ""
    try:
        return int(raw) if raw else default
    except (ValueError, TypeError):
        return default


def _env_bool(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _emit_audit_row(*, row, provider: str, reason: str, detail: str, dry_run: bool) -> None:
    """Write an ``LMSPushGradeAudit`` row capturing this auto-prune event.

    Tagged with ``course_id="_auto_prune"`` so the diagnostics dashboard
    can partition this stream from health-check / rotation streams.
    """
    try:
        from apps.integrations_marketplace.models import LMSPushGradeAudit

        school_id = str(getattr(row, "school_id", "") or "")
        user_hash = hashlib.sha256(school_id.encode("utf-8")).hexdigest()[:16]
        LMSPushGradeAudit.objects.create(  # tenant-isolation-allow: lms-oauth-auto-prune-platform-scope-celery-beat
            school_id=row.school_id if school_id else None,
            provider=provider,
            course_id=_PRUNE_COURSE_ID,
            assignment_id=("dry_run:" + reason) if dry_run else reason,
            user_hash=user_hash,
            score_text="",
            ok=False,
            status_code=0,
            detail=detail[:512],
            actor_user_id=None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("lms_oauth_auto_prune: audit-row emit failed: %s", exc)


def _prune_row(row) -> tuple[bool, str]:
    """Clear both access_token and refresh_token on a row.

    Returns ``(ok, error_reason)``.
    """
    try:
        row.access_token = ""
        row.refresh_token = ""
        row.save(update_fields=["access_token", "refresh_token", "updated_at"])
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, f"save_failed: {exc}"


def sweep_lms_oauth_auto_prune(
    *,
    now=None,
    max_rows: int | None = None,
    dry_run: bool | None = None,
) -> dict[str, Any]:
    """Find every LMSConnectorToken row whose ``expires_at`` has already
    passed AND that carries a refresh_token; classify each via the
    rotation probe; auto-prune (clear both tokens) on ``refresh_revoked``.

    Returns:
        ``{"considered": N, "pruned": K, "kept": M, "skipped": [...],
        "results": [...], "dry_run": bool}``

    NEVER raises.
    """
    from django.utils import timezone as _tz

    if max_rows is None:
        max_rows = _env_int("RMC_LMS_OAUTH_AUTO_PRUNE_MAX_ROWS", DEFAULT_MAX_ROWS)
    if dry_run is None:
        dry_run = _env_bool("RMC_LMS_OAUTH_AUTO_PRUNE_DRY_RUN")
    now = now or _tz.now()

    try:
        from apps.integrations_marketplace.models import LMSConnectorToken
    except Exception as exc:  # noqa: BLE001
        logger.debug("lms_oauth_auto_prune: token model unavailable: %s", exc)
        return {
            "considered": 0, "pruned": 0, "kept": 0,
            "skipped": [], "results": [], "dry_run": bool(dry_run),
            "error": str(exc),
        }

    from apps.integrations_marketplace.lms_token_rotation import (
        _attempt_refresh_probe, _classify_failure,
    )

    qs = LMSConnectorToken.objects.filter(  # tenant-isolation-allow: lms-oauth-auto-prune-platform-scope-celery-beat
        expires_at__lt=now,
        expires_at__isnull=False,
    ).exclude(refresh_token="")
    rows = list(qs[:max_rows])

    results: list[dict[str, Any]] = []
    pruned = 0
    kept = 0
    skipped: list[dict[str, Any]] = []
    for row in rows:
        provider = (getattr(row, "provider", "") or "").lower()
        if provider not in {"canvas", "moodle", "google"}:
            skipped.append({"row_id": row.pk, "reason": "unsupported_provider"})
            continue
        probe = _attempt_refresh_probe(row, provider)
        if probe.get("ok"):
            # Refresh succeeded — row is healthy, no prune action needed.
            kept += 1
            results.append({"row_id": row.pk, "provider": provider, "outcome": "kept"})
            continue
        reason = _classify_failure(probe)
        if reason != "refresh_revoked":
            kept += 1
            results.append({
                "row_id": row.pk, "provider": provider,
                "outcome": "kept", "reason": reason,
            })
            continue
        # Revoked — auto-prune.
        detail = str(probe.get("detail") or "")
        if dry_run:
            _emit_audit_row(row=row, provider=provider, reason=reason, detail=detail, dry_run=True)
            results.append({
                "row_id": row.pk, "provider": provider,
                "outcome": "would_prune", "reason": reason,
            })
            pruned += 1
            continue
        ok, err = _prune_row(row)
        _emit_audit_row(row=row, provider=provider, reason=reason, detail=detail, dry_run=False)
        if ok:
            pruned += 1
            results.append({"row_id": row.pk, "provider": provider, "outcome": "pruned", "reason": reason})
            logger.info(
                "lms_oauth_auto_prune: pruned row=%s provider=%s reason=%s",
                row.pk, provider, reason,
            )
        else:
            kept += 1
            results.append({
                "row_id": row.pk, "provider": provider,
                "outcome": "save_failed", "reason": err,
            })

    return {
        "considered": len(rows),
        "pruned": pruned,
        "kept": kept,
        "skipped": skipped,
        "results": results,
        "max_rows": max_rows,
        "dry_run": bool(dry_run),
    }


# ---------------------------------------------------------------------------
# Celery wrapper (registered lazily when celery is importable).
# ---------------------------------------------------------------------------
try:
    from celery import shared_task  # type: ignore

    @shared_task(name="integrations_marketplace.auto_prune_revoked_lms_tokens")
    def auto_prune_revoked_lms_tokens() -> dict[str, Any]:
        """Celery beat entry — runs ``sweep_lms_oauth_auto_prune`` with defaults."""
        return sweep_lms_oauth_auto_prune()
except Exception:  # pragma: no cover - celery not installed in some environments
    auto_prune_revoked_lms_tokens = None  # type: ignore[assignment]
