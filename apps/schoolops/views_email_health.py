"""v3.57.x Wave 8 Agent C — Operator email-health dashboard.

Endpoints (staff-only):

  * ``GET  /super/email/health/``  — :class:`EmailHealthDashboardView`
    renders four panels: resolved SMTP config (host/port/use_tls/
    from_email — NEVER password), last-24h delivery stats, top-5 most
    recent failures (redacted), config-source indicator.
  * ``POST /super/email/health/probe/`` — :class:`SmtpProbeJsonView`
    runs a synchronous SMTP probe and returns JSON.

Permission model: ``staff_member_required``. URL patterns carry
``# rbac-allow: super-staff-email-health-dashboard``.

Defensive contract:
  * Templates NEVER receive raw recipient emails — only ``to_hash``
    (12 hex chars) and coarse ``error_kind`` labels.
  * Passwords are never rendered, returned, or logged.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View


logger = logging.getLogger(__name__)


# Keys we strip out of the resolved-config dict before rendering. The
# resolver returns a plaintext password when configured; the template
# must NEVER receive it.
_REDACT_KEYS = ("host_password",)


def _safe_resolved_config_for_render() -> dict:
    """Return the resolved SMTP config dict with secrets redacted."""
    from apps.schoolops.email_delivery import get_resolved_smtp_config

    cfg = dict(get_resolved_smtp_config())
    for k in _REDACT_KEYS:
        cfg.pop(k, None)
    # Add a boolean for the template — "do we have a password configured?"
    # without revealing what it is.
    pwd_present_flag = False
    try:
        from apps.schoolops.email_delivery import get_resolved_smtp_config as _r

        full = _r()
        pwd_present_flag = bool((full.get("host_password") or "").strip())
    except Exception:  # noqa: BLE001
        pwd_present_flag = False
    cfg["host_password_configured"] = pwd_present_flag
    return cfg


@method_decorator(staff_member_required, name="dispatch")
class EmailHealthDashboardView(View):
    """Operator dashboard: SMTP config + delivery stats + recent failures.

    Auto-refreshes every 60s (template-level ``<meta http-equiv="refresh">``).
    The dashboard is read-only; the probe action is a separate POST view.
    """

    template_name = "schoolops/super/email_health.html"

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        from apps.schoolops.email_delivery import (
            get_recent_delivery_stats,
            get_recent_failures,
        )

        resolved = _safe_resolved_config_for_render()
        stats = get_recent_delivery_stats(window_hours=24)
        failures = get_recent_failures(limit=5)

        config_source_label = (
            "operator override (SiteSettings.email_delivery)"
            if resolved.get("source") == "site_settings_override"
            else "environment variables"
        )

        ctx = {
            "page_title": "Email delivery health",
            "resolved_config": resolved,
            "config_source": resolved.get("source") or "env",
            "config_source_label": config_source_label,
            "stats": stats,
            "failures": failures,
            "refresh_seconds": 60,
        }
        return render(request, self.template_name, ctx)


@method_decorator(staff_member_required, name="dispatch")
class SmtpProbeJsonView(View):
    """POST-only synchronous SMTP probe. Returns ``{ok, latency_ms, error}``."""

    http_method_names = ["post"]

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        from apps.schoolops.email_delivery import smtp_probe

        try:
            result = smtp_probe(timeout=5.0)
        except Exception as exc:  # noqa: BLE001  — view boundary
            logger.exception(
                "schoolops.email_health.probe_crashed err_type=%s",
                type(exc).__name__,
            )
            result = {
                "ok": False,
                "latency_ms": 0,
                "error": type(exc).__name__,
            }
        # Defensive: never echo a password back.
        result.pop("host_password", None)
        return JsonResponse(result, json_dumps_params={"sort_keys": True})


# Optional helper for callers that prefer plain JSON over a JsonResponse.
def _dashboard_payload_as_json() -> str:
    """Return the dashboard panel data as a JSON string (for tests/debug)."""
    from apps.schoolops.email_delivery import (
        get_recent_delivery_stats,
        get_recent_failures,
    )

    payload = {
        "resolved_config": _safe_resolved_config_for_render(),
        "stats": get_recent_delivery_stats(window_hours=24),
        "failures": get_recent_failures(limit=5),
    }
    return json.dumps(payload, sort_keys=True, default=str)


__all__ = [
    "EmailHealthDashboardView",
    "SmtpProbeJsonView",
]
