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

import datetime as _dt
import json
import logging
import time
from typing import Any

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import (
    HttpRequest,
    HttpResponse,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View


logger = logging.getLogger(__name__)


# v3.58.x Wave 9 Agent M — SSE stream caps.
_DEFAULT_SSE_HEARTBEAT_SECONDS = 5
_DEFAULT_SSE_MAX_DURATION_SECONDS = 300  # 5 minutes; operator can re-open


# Keys we strip out of the resolved-config dict before rendering. The
# resolver returns a plaintext password when configured; the template
# must NEVER receive it.
_REDACT_KEYS = ("host_password",)


def _get_bounce_rate_panel() -> dict:
    """Return bounce counts in 24h / 7d / 30d windows + per-kind breakdown.

    Shape::

        {
          "window_24h": {"total": int, "by_kind": {kind: int, ...}},
          "window_7d":  {"total": int, "by_kind": {kind: int, ...}},
          "window_30d": {"total": int, "by_kind": {kind: int, ...}},
        }

    Best-effort: returns zeros / empty maps on any error.
    """
    out = {
        "window_24h": {"total": 0, "by_kind": {}},
        "window_7d":  {"total": 0, "by_kind": {}},
        "window_30d": {"total": 0, "by_kind": {}},
    }
    try:
        from django.db.models import Count
        from django.utils import timezone

        from apps.schoolops.models_email_delivery import EmailDeliveryEvent

        now = timezone.now()
        windows = {
            "window_24h": now - _dt.timedelta(hours=24),
            "window_7d": now - _dt.timedelta(days=7),
            "window_30d": now - _dt.timedelta(days=30),
        }
        for key, cutoff in windows.items():
            # tenant-isolation-allow: platform-email-delivery-log-no-tenant-scope
            qs = EmailDeliveryEvent.objects.filter(
                bounced=True, created_at__gte=cutoff,
            )
            # tenant-isolation-allow: platform-email-delivery-log-no-tenant-scope
            total = qs.count()
            # tenant-isolation-allow: platform-email-delivery-log-no-tenant-scope
            grouped = (
                qs.values("bounce_kind")
                .annotate(n=Count("id"))
                .order_by("-n")
            )
            by_kind = {
                (row.get("bounce_kind") or "unknown"): int(row.get("n") or 0)
                for row in grouped
            }
            out[key] = {"total": int(total), "by_kind": by_kind}
    except Exception as exc:  # broad-by-design — dashboard reader, never raise
        logger.warning(
            "schoolops.email_health.bounce_panel_failed err_type=%s",
            type(exc).__name__,
        )
    return out


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
        # v3.58.x Wave 9 Agent M — bounce-rate panel.
        bounce_panel = _get_bounce_rate_panel()

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
            "bounce_panel": bounce_panel,
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


def _resolve_sse_heartbeat_seconds() -> int:
    """Resolve ``settings.SCHOOLOPS_EMAIL_DELIVERY_SSE_HEARTBEAT_SECONDS``."""
    raw = getattr(
        settings,
        "SCHOOLOPS_EMAIL_DELIVERY_SSE_HEARTBEAT_SECONDS",
        _DEFAULT_SSE_HEARTBEAT_SECONDS,
    )
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_SSE_HEARTBEAT_SECONDS
    if val < 1:
        return _DEFAULT_SSE_HEARTBEAT_SECONDS
    if val > 60:
        # Clamp absurd values — operator typo guard.
        return 60
    return val


def _build_live_counts_payload() -> dict:
    """Return the JSON-serializable live counts dict for SSE consumers.

    Shape::

        {
          "ts": "<ISO timestamp>",
          "sent_24h": int,
          "failed_24h": int,
          "bounced_24h": int,
        }
    """
    from apps.schoolops.email_delivery import get_recent_delivery_stats

    out = {
        "ts": "",
        "sent_24h": 0,
        "failed_24h": 0,
        "bounced_24h": 0,
    }
    try:
        from django.utils import timezone

        out["ts"] = timezone.now().isoformat()
        stats = get_recent_delivery_stats(window_hours=24)
        out["sent_24h"] = int(stats.get("sent_count") or 0)
        out["failed_24h"] = int(stats.get("failed_count") or 0)
        panel = _get_bounce_rate_panel()
        out["bounced_24h"] = int(panel.get("window_24h", {}).get("total") or 0)
    except Exception as exc:  # broad-by-design — SSE generator, never raise
        logger.warning(
            "schoolops.email_health.sse_payload_failed err_type=%s",
            type(exc).__name__,
        )
    return out


@method_decorator(staff_member_required, name="dispatch")
class EmailHealthStreamView(View):
    """SSE: stream sent/failed/bounced 24h counts every N seconds.

    GET ``/super/email/health/stream/`` — returns ``text/event-stream``.
    Each event is a single JSON object on a ``data:`` line. Stream
    self-closes after 5 minutes (operator can re-open via the
    ``EventSource`` auto-reconnect).

    HEARTBEAT cadence configurable via
    ``settings.SCHOOLOPS_EMAIL_DELIVERY_SSE_HEARTBEAT_SECONDS`` (default 5,
    clamped to [1, 60]).

    Honors ``Last-Event-ID`` (HTTP header
    ``HTTP_LAST_EVENT_ID``) by simply seeding ``next_event_id`` to
    ``int(received) + 1`` — events are not persisted, so resume from a
    past ID is best-effort (live tail, never replay).
    """

    http_method_names = ["get"]

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        heartbeat = _resolve_sse_heartbeat_seconds()
        max_duration = _DEFAULT_SSE_MAX_DURATION_SECONDS

        try:
            last_event_id = int(request.META.get("HTTP_LAST_EVENT_ID") or 0)
        except (TypeError, ValueError):
            last_event_id = 0
        next_event_id = max(0, last_event_id) + 1

        def _stream():
            # SSE preamble — comment line, browser-friendly.
            yield ": connected\n\n"
            started = time.monotonic()
            event_id = next_event_id
            while True:
                # Stop after max_duration; browser auto-reconnects to
                # this endpoint anyway.
                if (time.monotonic() - started) >= max_duration:
                    yield ": closing-after-max-duration\n\n"
                    return
                try:
                    payload = _build_live_counts_payload()
                    body = json.dumps(payload, sort_keys=True)
                except Exception as exc:  # broad-by-design — never break stream
                    logger.warning(
                        "schoolops.email_health.sse_payload_serialize_failed "
                        "err_type=%s",
                        type(exc).__name__,
                    )
                    body = json.dumps({"ok": False, "error": "serialize_failed"})
                yield f"id: {event_id}\nevent: heartbeat\ndata: {body}\n\n"
                event_id += 1
                try:
                    time.sleep(heartbeat)
                except Exception:  # noqa: BLE001 — sleep itself never crashes
                    return

        response = StreamingHttpResponse(
            _stream(),
            content_type="text/event-stream",
        )
        # Standard SSE-friendly headers — disable proxy buffering.
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


__all__ = [
    "EmailHealthDashboardView",
    "SmtpProbeJsonView",
    "EmailHealthStreamView",
]
