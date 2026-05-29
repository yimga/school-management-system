"""v4.00.59 — LMS connector OAuth health beat.

Reactive companion to v4.00.53's proactive ``lms_token_refresh``: walks
``LMSConnectorToken`` rows whose ``expires_at`` has ALREADY passed AND that
carry a refresh token; attempts a refresh via the existing
``apps.api.lms_adapters`` SOT; records every outcome as an
``LMSPushGradeAudit`` row tagged with ``course_id="_health_check"`` so the
operator diagnostics dashboard (``/super/migration/lms/diagnostics/``)
surfaces the result in the existing 24h rollups.

Pure-Python sweep:

  ``sweep_lms_oauth_health(now=None, max_rows=None) -> dict``

Celery wrapper (registered when celery is importable):

  ``apps.integrations_marketplace.auto_refresh_expired_lms_tokens``

NEVER raises — failures are captured in the per-row result list and
audit-row writes are wrapped in try/except so a single broken row never
aborts the sweep.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MAX_ROWS = 500
_HEALTH_COURSE_ID = "_health_check"


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name) or ""
    try:
        return int(raw) if raw else default
    except (ValueError, TypeError):
        return default


def _emit_audit_row(*, row, provider: str, outcome: dict[str, Any]) -> None:
    """Write an ``LMSPushGradeAudit`` row capturing this health-check attempt.

    Tagged with ``course_id="_health_check"`` so the v4.00.55 diagnostics
    rotation/push partitioning treats it as a separate stream. Hashed
    school identifier as user_hash (PII-safe).
    """
    try:
        import hashlib
        from apps.integrations_marketplace.models import LMSPushGradeAudit

        ok = bool(outcome.get("refreshed"))
        status_code = int(outcome.get("status_code") or (200 if ok else 0))
        detail = str(outcome.get("reason") or ("ok" if ok else "failed"))[:512]
        school_id = str(getattr(row, "school_id", "") or "")
        user_hash = hashlib.sha256(school_id.encode("utf-8")).hexdigest()[:16]
        LMSPushGradeAudit.objects.create(  # tenant-isolation-allow: lms-oauth-health-beat-audit-platform-scope
            school_id=row.school_id if school_id else None,
            provider=provider,
            course_id=_HEALTH_COURSE_ID,
            assignment_id="",
            user_hash=user_hash,
            score_text="",
            ok=ok,
            status_code=status_code,
            detail=detail,
            actor_user_id=None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("lms_oauth_health: audit-row emit failed: %s", exc)


def sweep_lms_oauth_health(
    *,
    now=None,
    max_rows: int | None = None,
) -> dict[str, Any]:
    """Find every LMSConnectorToken row whose ``expires_at`` has already
    passed AND that carries a refresh_token; attempt to refresh each.

    Returns:
        ``{"considered": N, "refreshed": K, "failed": F, "skipped": [...],
        "results": [...]}``  — audit-shape. Never raises.
    """
    from django.utils import timezone as _tz

    if max_rows is None:
        max_rows = _env_int("RMC_LMS_OAUTH_HEALTH_MAX_ROWS", DEFAULT_MAX_ROWS)
    now = now or _tz.now()

    try:
        from apps.integrations_marketplace.models import LMSConnectorToken
    except Exception as exc:  # noqa: BLE001
        logger.debug("lms_oauth_health: token model unavailable: %s", exc)
        return {"considered": 0, "refreshed": 0, "failed": 0, "skipped": [], "results": [], "error": str(exc)}

    from apps.integrations_marketplace.lms_token_refresh import _refresh_one

    qs = LMSConnectorToken.objects.filter(  # tenant-isolation-allow: lms-oauth-health-platform-scope-celery-beat
        expires_at__lt=now,
        expires_at__isnull=False,
    ).exclude(refresh_token="")
    rows = list(qs[:max_rows])

    results: list[dict[str, Any]] = []
    refreshed = 0
    failed = 0
    skipped: list[dict[str, Any]] = []
    for row in rows:
        provider = (getattr(row, "provider", "") or "").lower()
        if provider not in {"canvas", "moodle", "google"}:
            skipped.append({"row_id": row.pk, "reason": "unsupported_provider"})
            continue
        outcome = _refresh_one(row, provider)
        _emit_audit_row(row=row, provider=provider, outcome=outcome)
        results.append({"row_id": row.pk, "provider": provider, **outcome})
        if outcome.get("refreshed"):
            refreshed += 1
        else:
            failed += 1
            logger.info(
                "lms_oauth_health: row=%s provider=%s reason=%s",
                row.pk, provider, outcome.get("reason"),
            )

    return {
        "considered": len(rows),
        "refreshed": refreshed,
        "failed": failed,
        "skipped": skipped,
        "results": results,
        "max_rows": max_rows,
    }


# ---------------------------------------------------------------------------
# Celery wrapper (registered lazily when celery is importable).
# ---------------------------------------------------------------------------
try:
    from celery import shared_task  # type: ignore

    @shared_task(name="integrations_marketplace.auto_refresh_expired_lms_tokens")
    def auto_refresh_expired_lms_tokens() -> dict[str, Any]:
        """Celery beat entry — runs ``sweep_lms_oauth_health`` with defaults."""
        return sweep_lms_oauth_health()
except Exception:  # pragma: no cover - celery not installed in some environments
    auto_refresh_expired_lms_tokens = None  # type: ignore[assignment]
