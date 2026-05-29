"""v4.00.56 — LMS connector diagnostics operator dashboard.

Surfaces live token-health metrics so on-call can spot a misconfigured
or stale LMS integration before pushgrade traffic starts failing:

  * per-provider token count + how many are configured (have an access
    token) vs unconfigured stubs
  * tokens past their stated ``expires_at`` (expired by the wall clock)
  * tokens past the rotation grace window (7d after expiry, per
    :mod:`apps.integrations_marketplace.lms_token_rotation`)
  * tokens missing a refresh token (cannot recover unattended)
  * last-24h push-grade audit outcomes per provider (ok / failed)
  * last-24h rotation outcomes per provider
  * timestamp of the most recent successful refresh per provider

Surface is staff-only and read-only. Designed to be polled by external
monitors via ``?format=json``.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

_DIAG_LOOKBACK_HOURS = 24
_ROTATION_GRACE_SECONDS = 7 * 24 * 60 * 60  # mirrors lms_token_rotation default


def _compute_lms_diagnostics() -> dict:
    """Pure-function aggregator. Returns a dict the view renders as either
    JSON or template-context. NEVER raises — wraps each section in try/except
    and surfaces ``error`` flags per section."""
    out: dict = {
        "generated_at": timezone.now().isoformat(),
        "lookback_hours": _DIAG_LOOKBACK_HOURS,
        "rotation_grace_seconds": _ROTATION_GRACE_SECONDS,
        "providers": [],
        "totals": {
            "configured": 0,
            "unconfigured": 0,
            "expired": 0,
            "past_grace": 0,
            "missing_refresh": 0,
        },
        "errors": [],
    }

    try:
        from apps.integrations_marketplace.models_lms_token import LMSConnectorToken
    except Exception as exc:  # noqa: BLE001
        out["errors"].append(f"token_model_unavailable: {exc}")
        return out

    try:
        from apps.integrations_marketplace.models_lms_audit import LMSPushGradeAudit
    except Exception as exc:  # noqa: BLE001
        LMSPushGradeAudit = None  # type: ignore[assignment]
        out["errors"].append(f"audit_model_unavailable: {exc}")

    now = timezone.now()
    grace_cutoff = now - timedelta(seconds=_ROTATION_GRACE_SECONDS)
    audit_since = now - timedelta(hours=_DIAG_LOOKBACK_HOURS)

    by_provider: dict[str, dict] = {}
    try:
        for row in LMSConnectorToken.objects.all().iterator(chunk_size=500):  # tenant-isolation-allow: lms-diagnostics-platform-scope-staff-only
            p = row.provider or ""
            d = by_provider.setdefault(p, {
                "provider": p,
                "total": 0,
                "configured": 0,
                "unconfigured": 0,
                "expired": 0,
                "past_grace": 0,
                "missing_refresh": 0,
                "latest_refresh_at": "",
            })
            d["total"] += 1
            configured = bool(row.access_token)
            if configured:
                d["configured"] += 1
                out["totals"]["configured"] += 1
            else:
                d["unconfigured"] += 1
                out["totals"]["unconfigured"] += 1
            if row.expires_at and row.expires_at < now:
                d["expired"] += 1
                out["totals"]["expired"] += 1
            if row.expires_at and row.expires_at < grace_cutoff:
                d["past_grace"] += 1
                out["totals"]["past_grace"] += 1
            if configured and not row.refresh_token:
                d["missing_refresh"] += 1
                out["totals"]["missing_refresh"] += 1
            # Track newest updated_at as a refresh-recency proxy (the existing
            # row only carries one timestamp; specific refresh history lives in
            # audit rows handled below).
            iso = row.updated_at.isoformat() if row.updated_at else ""
            if iso > d["latest_refresh_at"]:
                d["latest_refresh_at"] = iso
    except Exception as exc:  # noqa: BLE001
        logger.warning("lms_diagnostics: token enum failed: %s", exc)
        out["errors"].append(f"token_enum_failed: {exc}")

    # Push-grade + rotation audit rollups per provider.
    if LMSPushGradeAudit is not None:
        try:
            rotation_marker = "_rotation"
            qs = LMSPushGradeAudit.objects.filter(created_at__gte=audit_since)  # tenant-isolation-allow: lms-diagnostics-audit-rollup-staff-only
            for r in qs.iterator(chunk_size=1000):
                p = r.provider or ""
                d = by_provider.setdefault(p, {
                    "provider": p, "total": 0, "configured": 0, "unconfigured": 0,
                    "expired": 0, "past_grace": 0, "missing_refresh": 0,
                    "latest_refresh_at": "",
                })
                is_rot = (r.course_id == rotation_marker)
                if is_rot:
                    d.setdefault("rotation_ok_24h", 0)
                    d.setdefault("rotation_failed_24h", 0)
                    if r.ok:
                        d["rotation_ok_24h"] += 1
                    else:
                        d["rotation_failed_24h"] += 1
                else:
                    d.setdefault("push_ok_24h", 0)
                    d.setdefault("push_failed_24h", 0)
                    if r.ok:
                        d["push_ok_24h"] += 1
                    else:
                        d["push_failed_24h"] += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("lms_diagnostics: audit rollup failed: %s", exc)
            out["errors"].append(f"audit_rollup_failed: {exc}")

    # Default missing-key zeros so JSON consumers get a stable shape.
    for d in by_provider.values():
        for k in ("push_ok_24h", "push_failed_24h", "rotation_ok_24h", "rotation_failed_24h"):
            d.setdefault(k, 0)

    out["providers"] = sorted(by_provider.values(), key=lambda r: r.get("provider", ""))
    return out


@staff_member_required
@require_http_methods(["GET"])
def lms_diagnostics(request: HttpRequest):
    """v4.00.56 — Operator dashboard at /super/migration/lms/diagnostics/."""
    diag = _compute_lms_diagnostics()
    if (request.GET.get("format") or "").lower() == "json":
        return JsonResponse({"success": not diag["errors"], **diag})
    return render(request, "migration_cloud/super/lms_diagnostics.html", {"diag": diag})
