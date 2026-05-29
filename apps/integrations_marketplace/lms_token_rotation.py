"""v4.00.54 — LMS connector token-ROTATION sweep (Celery beat).

Distinct purpose from v4.00.53's ``lms_token_refresh.sweep_lms_tokens_due_refresh``:

* **Refresh** = proactively exchange the refresh_token for a fresh access_token
  before ``expires_at``. Cheap, fully automatic, daily.
* **Rotation** = detect rows where the REFRESH leg itself has failed (or
  is going to fail forever) and surface them to operators so they can
  re-authorize via the v4.00.53 PKCE flow.

This sweep catches the cliff cases the refresh beat cannot fix on its
own. For each ``LMSConnectorToken`` it considers:

  1. ``expires_at`` passed more than ``rotation_grace_seconds`` ago AND
     ``refresh_token`` empty → rotation-needed: ``"refresh_missing"``.
  2. ``expires_at`` passed more than ``rotation_grace_seconds`` ago AND
     refresh attempt returns ``invalid_grant`` / 400 / 401 → rotation-needed:
     ``"refresh_revoked"`` (the refresh_token has been invalidated upstream
     because the user rotated their LMS password or revoked OAuth grant).
  3. Provider unsupported by adapter SOT → rotation-needed:
     ``"unsupported_provider"``.

Outcome for rotation-needed rows: clear ``access_token`` (so the next
inline use triggers the operator console reconnect flow) AND emit an
``LMSPushGradeAudit`` "rotation_required" row so operators have a paper
trail. The refresh_token is preserved as-is — operators may still want
to inspect it (in encrypted form) before fully re-authorizing.

Operator-overridable env vars
-----------------------------

* ``RMC_LMS_TOKEN_ROTATION_GRACE_SECONDS`` — default 7 days
  (``7 * 24 * 60 * 60 = 604_800``). Anything younger than the grace
  is left to the inline middleware + refresh beat.
* ``RMC_LMS_TOKEN_ROTATION_DISABLED`` — set to ``"1"`` to no-op the
  whole sweep (useful for staged rollout).

Pure-Python sweep:

  ``sweep_lms_tokens_due_rotation(grace_seconds=604_800, now=None) -> dict``

Celery wrapper (registered when celery is importable):

  ``apps.integrations_marketplace.rotate_due_lms_tokens``

Failures are bounded and surfaced in the per-row result list — the
sweep itself NEVER raises.
"""
from __future__ import annotations

import logging
import os
from datetime import timedelta
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_GRACE_SECONDS = 7 * 24 * 60 * 60  # 7 days
_REVOKED_HINTS = ("invalid_grant", "invalid_token", "unauthorized_client", "revoked")
_REVOKED_STATUS_CODES = {400, 401, 403}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name) or ""
    try:
        return int(raw) if raw else default
    except (ValueError, TypeError):
        return default


def _env_bool(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_client_creds(provider: str) -> tuple[str, str]:
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


def _record_rotation_audit(row, reason: str, detail: str = "") -> None:
    """Best-effort: write an LMSPushGradeAudit row with the rotation event.

    Uses the existing audit table because operators already poll the
    audit operator UI at ``/portal/super/integrations/lms/audit/`` — no
    new surface needed. ``course_id`` is set to ``"_rotation"`` so the
    rotation rows are filterable.
    """
    try:
        from apps.integrations_marketplace.models import LMSPushGradeAudit
    except Exception as exc:  # noqa: BLE001
        logger.debug("lms_token_rotation: audit model unavailable: %s", exc)
        return
    try:
        LMSPushGradeAudit.objects.create(  # tenant-isolation-allow: lms-token-rotation-platform-scope-celery-beat
            school_id=getattr(row, "school_id", None),
            provider=getattr(row, "provider", "") or "",
            course_id="_rotation",
            assignment_id=reason,
            user_hash="",
            score_text="",
            ok=False,
            status_code=0,
            detail=detail[:255],
            actor_user_id="",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("lms_token_rotation: audit insert failed row=%s reason=%s: %s",
                       getattr(row, "pk", "?"), reason, exc)


def _attempt_refresh_probe(row, provider: str) -> dict[str, Any]:
    """Probe the refresh leg once. Caller uses the result to classify the row."""
    from apps.api import lms_adapters

    cid, csec = _resolve_client_creds(provider)
    if not cid or not csec:
        return {"ok": False, "reason": "client_creds_missing"}
    kwargs: dict[str, Any] = {
        "refresh_token": row.refresh_token,
        "client_id": cid,
        "client_secret": csec,
    }
    if provider == "canvas":
        kwargs["base_url"] = getattr(row, "base_url", "") or ""
    try:
        return lms_adapters.refresh_token(provider, **kwargs)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"adapter_raise: {exc}"}


def _classify_failure(result: dict[str, Any]) -> str:
    """Map a refresh-leg failure dict to a rotation reason."""
    detail = (result.get("detail") or "").lower()
    code = result.get("status_code") or 0
    if any(hint in detail for hint in _REVOKED_HINTS):
        return "refresh_revoked"
    if code in _REVOKED_STATUS_CODES:
        return "refresh_revoked"
    return "refresh_failed"


def _clear_access_token(row) -> bool:
    """Zero the access_token so the next inline use triggers reconnect.

    Preserves refresh_token (operators may inspect). Returns True on success.
    """
    from django.utils import timezone as _tz

    try:
        row.access_token = ""
        row.expires_at = _tz.now() - timedelta(seconds=1)
        row.save(update_fields=["access_token", "expires_at", "updated_at"])
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("lms_token_rotation: clear failed row=%s: %s", getattr(row, "pk", "?"), exc)
        return False


def sweep_lms_tokens_due_rotation(
    *,
    grace_seconds: int | None = None,
    now=None,
) -> dict[str, Any]:
    """Find LMSConnectorToken rows past the rotation grace window and
    classify each as ``rotation_required`` or ``still_healthy``.

    Returns:
        ``{"considered": N, "rotated": K, "still_healthy": M, "results": [...]}``
        — per-row audit shape. Never raises.
    """
    if _env_bool("RMC_LMS_TOKEN_ROTATION_DISABLED"):
        return {"considered": 0, "rotated": 0, "still_healthy": 0, "results": [], "disabled": True}

    from django.utils import timezone as _tz

    if grace_seconds is None:
        grace_seconds = _env_int("RMC_LMS_TOKEN_ROTATION_GRACE_SECONDS", DEFAULT_GRACE_SECONDS)
    now = now or _tz.now()
    cutoff = now - timedelta(seconds=grace_seconds)

    try:
        from apps.integrations_marketplace.models import LMSConnectorToken
    except Exception as exc:  # noqa: BLE001
        logger.debug("lms_token_rotation: model unavailable: %s", exc)
        return {"considered": 0, "rotated": 0, "still_healthy": 0, "results": [], "error": str(exc)}

    qs = LMSConnectorToken.objects.filter(  # tenant-isolation-allow: lms-token-rotation-platform-scope-celery-beat
        expires_at__lte=cutoff,
        expires_at__isnull=False,
    )
    rows = list(qs[:1000])

    results: list[dict[str, Any]] = []
    rotated = 0
    still_healthy = 0

    for row in rows:
        provider = (getattr(row, "provider", "") or "").lower()
        if provider not in {"canvas", "moodle", "google", "google_classroom"}:
            reason = "unsupported_provider"
            cleared = _clear_access_token(row)
            _record_rotation_audit(row, reason)
            results.append({"row_id": row.pk, "provider": provider, "outcome": "rotation_required",
                            "reason": reason, "cleared": cleared})
            rotated += 1
            continue

        if not getattr(row, "refresh_token", ""):
            reason = "refresh_missing"
            cleared = _clear_access_token(row)
            _record_rotation_audit(row, reason)
            results.append({"row_id": row.pk, "provider": provider, "outcome": "rotation_required",
                            "reason": reason, "cleared": cleared})
            rotated += 1
            continue

        probe_provider = "google" if provider == "google_classroom" else provider
        probe = _attempt_refresh_probe(row, probe_provider)
        if probe.get("ok") and probe.get("access_token"):
            # Refresh leg still works — this row is still healthy. Hand back
            # the new access_token so the operator's next call uses it.
            try:
                row.access_token = probe["access_token"]
                expires_in = int(probe.get("expires_in") or 0)
                if expires_in:
                    row.expires_at = now + timedelta(seconds=expires_in)
                row.save(update_fields=["access_token", "expires_at", "updated_at"])
            except Exception as exc:  # noqa: BLE001
                logger.warning("lms_token_rotation: heal save failed row=%s: %s", row.pk, exc)
            results.append({"row_id": row.pk, "provider": provider, "outcome": "still_healthy",
                            "reason": "refresh_succeeded"})
            still_healthy += 1
            continue

        reason = _classify_failure(probe)
        cleared = _clear_access_token(row)
        _record_rotation_audit(row, reason, detail=str(probe.get("detail") or "")[:255])
        results.append({"row_id": row.pk, "provider": provider, "outcome": "rotation_required",
                        "reason": reason, "cleared": cleared,
                        "status_code": probe.get("status_code")})
        rotated += 1

    return {
        "considered": len(rows),
        "rotated": rotated,
        "still_healthy": still_healthy,
        "results": results,
        "grace_seconds": grace_seconds,
    }


# ---------------------------------------------------------------------------
# Celery wrapper (registered lazily when celery is importable).
# ---------------------------------------------------------------------------
try:
    from celery import shared_task  # type: ignore

    @shared_task(name="integrations_marketplace.rotate_due_lms_tokens")
    def rotate_due_lms_tokens() -> dict[str, Any]:
        """Celery beat entry — runs ``sweep_lms_tokens_due_rotation`` with the
        configured grace. Return value is the audit dict (visible in
        flower/result-backend)."""
        return sweep_lms_tokens_due_rotation()
except Exception:  # pragma: no cover - celery not installed in some environments
    rotate_due_lms_tokens = None  # type: ignore[assignment]
