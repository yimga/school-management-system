"""v4.00.53 — LMS connector token-refresh sweep (Celery beat).

Proactively refreshes ``LMSConnectorToken`` rows whose ``expires_at`` falls
within ``RMC_LMS_TOKEN_REFRESH_WINDOW_SECONDS`` (default 24h = 86_400s) of
now. Pairs with the v4.00.52 60s synchronous middleware
``apps.portal.views_lms_console._maybe_proactive_refresh`` — this beat keeps
tokens fresh for offline batch jobs that don't trigger the inline path.

Pure-Python sweep:

  ``sweep_lms_tokens_due_refresh(window_seconds=86_400, now=None) -> dict``

Celery wrapper (registered when celery is importable):

  ``apps.integrations_marketplace.refresh_due_lms_tokens``

Failures are bounded and surfaced in the per-row result list — the sweep
itself NEVER raises.
"""
from __future__ import annotations

import logging
import os
from datetime import timedelta
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_SECONDS = 24 * 60 * 60  # 24h


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name) or ""
    try:
        return int(raw) if raw else default
    except (ValueError, TypeError):
        return default


def _resolve_client_creds(provider: str) -> tuple[str, str]:
    """Resolve ``RMC_LMS_<PROVIDER>_CLIENT_ID/_SECRET`` from settings/env.

    Returns ``("", "")`` when either is missing.
    """
    from django.conf import settings

    up = provider.upper()
    cid = (
        getattr(settings, f"RMC_LMS_{up}_CLIENT_ID", "")
        or os.environ.get(f"RMC_LMS_{up}_CLIENT_ID", "")
        or ""
    ).strip()
    csec = (
        getattr(settings, f"RMC_LMS_{up}_CLIENT_SECRET", "")
        or os.environ.get(f"RMC_LMS_{up}_CLIENT_SECRET", "")
        or ""
    ).strip()
    return cid, csec


def _refresh_one(row, provider: str) -> dict[str, Any]:
    """Refresh a single row in-place. Returns audit-shaped result dict."""
    from apps.api import lms_adapters

    if not getattr(row, "refresh_token", ""):
        return {"refreshed": False, "reason": "no_refresh_token"}
    cid, csec = _resolve_client_creds(provider)
    if not cid or not csec:
        return {"refreshed": False, "reason": "client_creds_missing"}

    kwargs: dict[str, Any] = {
        "refresh_token": row.refresh_token,
        "client_id": cid,
        "client_secret": csec,
    }
    if provider == "canvas":
        kwargs["base_url"] = getattr(row, "base_url", "") or ""

    try:
        result = lms_adapters.refresh_token(provider, **kwargs)
    except Exception as exc:  # noqa: BLE001
        return {"refreshed": False, "reason": f"adapter_raise: {exc}"}

    if not result.get("ok") or not result.get("access_token"):
        return {
            "refreshed": False,
            "reason": "refresh_failed",
            "status_code": result.get("status_code"),
            "detail": result.get("detail", ""),
        }

    from django.utils import timezone as _tz

    row.access_token = result["access_token"]
    expires_in = int(result.get("expires_in") or 0)
    if expires_in:
        row.expires_at = _tz.now() + timedelta(seconds=expires_in)
    try:
        row.save(update_fields=["access_token", "expires_at", "updated_at"])
    except Exception as exc:  # noqa: BLE001
        return {"refreshed": False, "reason": f"save_failed: {exc}"}
    return {"refreshed": True, "expires_in": expires_in}


def sweep_lms_tokens_due_refresh(
    *,
    window_seconds: int | None = None,
    now=None,
) -> dict[str, Any]:
    """Find every LMSConnectorToken row whose ``expires_at`` falls inside
    ``window_seconds`` of ``now`` AND that carries a refresh_token, then
    refresh each in-place.

    Returns:
        ``{"considered": N, "refreshed": K, "skipped": [...], "results":
        [...]}``  — per-row audit shape. Never raises.
    """
    from django.utils import timezone as _tz

    if window_seconds is None:
        window_seconds = _env_int("RMC_LMS_TOKEN_REFRESH_WINDOW_SECONDS", DEFAULT_WINDOW_SECONDS)
    now = now or _tz.now()
    cutoff = now + timedelta(seconds=window_seconds)

    try:
        from apps.integrations_marketplace.models import LMSConnectorToken
    except Exception as exc:  # noqa: BLE001
        logger.debug("lms_token_refresh: model unavailable: %s", exc)
        return {"considered": 0, "refreshed": 0, "skipped": [], "results": [], "error": str(exc)}

    qs = LMSConnectorToken.objects.filter(  # tenant-isolation-allow: lms-token-refresh-platform-scope-celery-beat
        expires_at__lte=cutoff,
        expires_at__isnull=False,
    ).exclude(refresh_token="")
    rows = list(qs[:1000])

    results: list[dict[str, Any]] = []
    refreshed = 0
    skipped: list[dict[str, Any]] = []
    for row in rows:
        provider = (getattr(row, "provider", "") or "").lower()
        if provider not in {"canvas", "moodle", "google"}:
            skipped.append({"row_id": row.pk, "reason": "unsupported_provider"})
            continue
        outcome = _refresh_one(row, provider)
        results.append({"row_id": row.pk, "provider": provider, **outcome})
        if outcome.get("refreshed"):
            refreshed += 1
        else:
            logger.info(
                "lms_token_refresh: row=%s provider=%s reason=%s",
                row.pk, provider, outcome.get("reason"),
            )
    return {
        "considered": len(rows),
        "refreshed": refreshed,
        "skipped": skipped,
        "results": results,
        "window_seconds": window_seconds,
    }


# ---------------------------------------------------------------------------
# Celery wrapper (registered lazily when celery is importable).
# ---------------------------------------------------------------------------
try:
    from celery import shared_task  # type: ignore

    @shared_task(name="integrations_marketplace.refresh_due_lms_tokens")
    def refresh_due_lms_tokens() -> dict[str, Any]:
        """Celery beat entry — runs ``sweep_lms_tokens_due_refresh`` with the
        configured window. Return value is the audit dict (visible in
        flower/result-backend)."""
        return sweep_lms_tokens_due_refresh()
except Exception:  # pragma: no cover - celery not installed in some environments
    refresh_due_lms_tokens = None  # type: ignore[assignment]
