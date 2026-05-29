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


# ---------------------------------------------------------------------------
# v4.00.59 — Operator action buttons: force-refresh + force-rotate per
# provider. POSTs land here from the diagnostics dashboard; CSRF-protected
# Django session auth via @staff_member_required.
# ---------------------------------------------------------------------------


def _safe_provider(raw: str) -> str:
    """Whitelist allow-list of provider slugs so the action endpoints can't
    be coerced into operating on arbitrary input."""
    p = (raw or "").strip().lower()
    return p if p in {"canvas", "moodle", "google_classroom", "google"} else ""


@staff_member_required
@require_http_methods(["POST"])
def lms_diagnostics_force_refresh(request: HttpRequest):
    """v4.00.59 — Force-refresh every expired token for ``?provider=<slug>``.

    Reuses v4.00.59 ``lms_oauth_health.sweep_lms_oauth_health`` so the
    outcome lands in the audit ring via the existing ``_health_check``
    marker. Returns JSON summary; redirects to the diagnostics page when
    the request is form-submitted (no Accept JSON header).
    """
    provider = _safe_provider(request.POST.get("provider") or request.GET.get("provider") or "")
    if not provider:
        return JsonResponse({"success": False, "error": "missing_or_bad_provider"}, status=400)

    try:
        from apps.integrations_marketplace.lms_oauth_health import sweep_lms_oauth_health
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"success": False, "error": f"sweep_unavailable: {exc}"}, status=503)

    out = sweep_lms_oauth_health()
    # Filter the result for the requested provider so the operator sees
    # only what was relevant to their click.
    by_provider = [r for r in out.get("results", []) if r.get("provider") == provider]
    summary = {
        "success": True,
        "action": "force_refresh",
        "provider": provider,
        "considered": out.get("considered", 0),
        "refreshed": out.get("refreshed", 0),
        "failed": out.get("failed", 0),
        "results_for_provider": by_provider,
    }

    if (request.headers.get("Accept") or "").lower().startswith("application/json"):
        return JsonResponse(summary)
    # Form-submitted: send the operator back to the dashboard.
    from django.http import HttpResponseRedirect
    return HttpResponseRedirect(
        f"/super/migration/lms/diagnostics/?action=force_refresh&provider={provider}"
        f"&considered={summary['considered']}&refreshed={summary['refreshed']}&failed={summary['failed']}"
    )


@staff_member_required
@require_http_methods(["POST"])
def lms_diagnostics_force_rotate(request: HttpRequest):
    """v4.00.59 — Force-rotate every token past the rotation-grace window
    for ``?provider=<slug>``.

    Reuses v4.00.54 ``lms_token_rotation.sweep_lms_tokens_due_rotation``.
    """
    provider = _safe_provider(request.POST.get("provider") or request.GET.get("provider") or "")
    if not provider:
        return JsonResponse({"success": False, "error": "missing_or_bad_provider"}, status=400)

    try:
        from apps.integrations_marketplace.lms_token_rotation import sweep_lms_tokens_due_rotation
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"success": False, "error": f"sweep_unavailable: {exc}"}, status=503)

    out = sweep_lms_tokens_due_rotation()
    by_provider = [r for r in out.get("results", []) if r.get("provider") == provider]
    summary = {
        "success": True,
        "action": "force_rotate",
        "provider": provider,
        "considered": out.get("considered", 0),
        "rotated": out.get("rotated", 0),
        "failed": out.get("failed", 0),
        "results_for_provider": by_provider,
    }

    if (request.headers.get("Accept") or "").lower().startswith("application/json"):
        return JsonResponse(summary)
    from django.http import HttpResponseRedirect
    return HttpResponseRedirect(
        f"/super/migration/lms/diagnostics/?action=force_rotate&provider={provider}"
        f"&considered={summary['considered']}&rotated={summary['rotated']}&failed={summary['failed']}"
    )
