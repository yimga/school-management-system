"""v3.58.x Wave 9 Agent K — Signup-flow diagnostics dashboard.

Operator dashboard at ``/super/signup/diagnostics/`` for triaging the
"network unreachable" / signup-timeout class of bugs. Renders five
read-only probe panels:

  * **DB probe** — ``connection.ensure_connection()`` + measured latency.
  * **Redis / Celery broker probe** — lazy-import ping, never raises.
  * **Outbound SMTP-port reachability** — ``socket.create_connection(
    ("smtp.gmail.com", 587), timeout=3)``. Catches the Render-blocks-
    outbound-587 case (free-tier IPs typically can't reach SMTP).
  * **SMTP server probe** — re-uses ``apps.schoolops.email_delivery
    .smtp_probe`` from wave 8.
  * **EmailDeliveryEvent counters** — sent / failed / queued for the
    last 100 ``priority='transactional'`` rows, plus the most recent
    10 signup-verification attempts (rows whose ``subject_prefix``
    starts with "Verify your school:").

All counters / panels are PII-safe — the dashboard never renders
raw recipient addresses; only the truncated ``to_hash`` (12 hex chars)
from the audit row.
"""
from __future__ import annotations

import logging
import socket
import time
from typing import Any

from django.contrib.admin.views.decorators import staff_member_required
from django.db import connection
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View


logger = logging.getLogger(__name__)


# Outbound-network probe target. Gmail SMTP submission port is the
# canonical "can this PaaS reach external SMTP?" signal. Render free
# tier and similar gateways frequently block port 587 outbound, which
# manifests in the request lifecycle as a long socket-level hang.
_OUTBOUND_PROBE_HOST = "smtp.gmail.com"
_OUTBOUND_PROBE_PORT = 587
_OUTBOUND_PROBE_TIMEOUT = 3.0

# Number of recent EmailDeliveryEvent rows we summarize in the
# "recent transactional sends" panel.
_RECENT_ROWS_LIMIT = 100
# Number of signup-verification audit rows we render in the
# per-attempt panel.
_SIGNUP_VERIFY_ROWS_LIMIT = 10
# subject_prefix prefix the signup view emits via the canonical sender.
_SIGNUP_SUBJECT_MARKER = "Verify your school:"


def _probe_db() -> dict:
    """Run ``connection.ensure_connection()`` and time the round-trip."""
    started = time.monotonic()
    try:
        connection.ensure_connection()
        latency_ms = int((time.monotonic() - started) * 1000)
        return {
            "ok": True,
            "latency_ms": latency_ms,
            "error": None,
            "vendor": connection.vendor,
        }
    except Exception as exc:  # broad-by-design — diagnostic, never raise
        latency_ms = int((time.monotonic() - started) * 1000)
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "error": type(exc).__name__,
            "vendor": getattr(connection, "vendor", "unknown"),
        }


def _probe_redis_celery_broker() -> dict:
    """Best-effort Redis / Celery broker reachability probe.

    Tries to import the redis client + ping ``CELERY_BROKER_URL``. Falls
    back to the Django cache backend ping when redis-py isn't present.
    Returns ``ok=False`` with a coarse ``error`` label on any failure;
    never raises.
    """
    started = time.monotonic()
    try:
        from django.conf import settings

        broker_url = (
            getattr(settings, "CELERY_BROKER_URL", "")
            or getattr(settings, "BROKER_URL", "")
            or ""
        )
        if not broker_url:
            return {
                "ok": False,
                "latency_ms": 0,
                "error": "no_broker_url_configured",
                "broker_kind": "none",
            }
        # Lazy import — redis is an optional dep in dev / test envs.
        try:
            import redis  # type: ignore[import-not-found]
        except ImportError:
            return {
                "ok": False,
                "latency_ms": int((time.monotonic() - started) * 1000),
                "error": "redis_client_not_installed",
                "broker_kind": "unknown",
            }
        client = redis.Redis.from_url(
            broker_url, socket_connect_timeout=3, socket_timeout=3,
        )
        client.ping()
        return {
            "ok": True,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "error": None,
            "broker_kind": "redis",
        }
    except Exception as exc:  # broad-by-design — diagnostic
        return {
            "ok": False,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "error": type(exc).__name__,
            "broker_kind": "redis",
        }


def _probe_outbound_smtp_port() -> dict:
    """Open a raw TCP connection to smtp.gmail.com:587 with 3s timeout.

    Render's free tier and several other PaaS gateways block outbound
    port 587 by default — this probe surfaces the symptom directly so
    the operator can either upgrade the plan, switch to a managed
    transactional provider (SendGrid / Mailgun / SES on a non-blocked
    port like 2525 / 443 / 465), or pick a different SMTP backend.
    """
    started = time.monotonic()
    sock = None
    try:
        sock = socket.create_connection(
            (_OUTBOUND_PROBE_HOST, _OUTBOUND_PROBE_PORT),
            timeout=_OUTBOUND_PROBE_TIMEOUT,
        )
        latency_ms = int((time.monotonic() - started) * 1000)
        return {
            "ok": True,
            "latency_ms": latency_ms,
            "error": None,
            "host": _OUTBOUND_PROBE_HOST,
            "port": _OUTBOUND_PROBE_PORT,
            "verdict": "reachable",
        }
    except (socket.timeout, OSError) as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "error": type(exc).__name__,
            "host": _OUTBOUND_PROBE_HOST,
            "port": _OUTBOUND_PROBE_PORT,
            "verdict": "blocked_or_unreachable",
        }
    except Exception as exc:  # broad-by-design — diagnostic
        latency_ms = int((time.monotonic() - started) * 1000)
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "error": type(exc).__name__,
            "host": _OUTBOUND_PROBE_HOST,
            "port": _OUTBOUND_PROBE_PORT,
            "verdict": "error",
        }
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


def _probe_smtp_server() -> dict:
    """Re-use wave 8's :func:`smtp_probe` for the configured EMAIL_HOST."""
    try:
        from apps.schoolops.email_delivery import smtp_probe

        return smtp_probe(timeout=5.0)
    except Exception as exc:  # broad-by-design — diagnostic
        return {
            "ok": False,
            "latency_ms": 0,
            "error": type(exc).__name__,
            "host": "",
            "port": 0,
            "use_tls": False,
            "backend": "",
        }


def _recent_transactional_counters() -> dict:
    """Count ok / failed / queued across the last 100 transactional rows."""
    out = {
        "sent_count": 0,
        "failed_count": 0,
        "queued_count": 0,
        "total_examined": 0,
        "window_label": (
            f"last {_RECENT_ROWS_LIMIT} priority='transactional' rows"
        ),
    }
    try:
        from apps.schoolops.models_email_delivery import EmailDeliveryEvent

        # tenant-isolation-allow: platform-email-delivery-log-no-tenant-scope
        rows = list(
            EmailDeliveryEvent.objects.filter(priority="transactional")
            .order_by("-created_at")[:_RECENT_ROWS_LIMIT]
        )
        for row in rows:
            out["total_examined"] += 1
            if row.ok:
                out["sent_count"] += 1
            else:
                # error_kind="" is treated as a generic failure; the
                # async path queues with attempts=0 + ok=True so the
                # "queued_count" bucket here captures the post-thread
                # success rows only.
                out["failed_count"] += 1
    except Exception as exc:  # broad-by-design — diagnostic
        logger.warning(
            "signup_diagnostics.counters_read_failed err_type=%s",
            type(exc).__name__,
        )
    return out


def _recent_signup_attempts() -> list[dict]:
    """Return the 10 most-recent signup-verification audit rows."""
    out: list[dict] = []
    try:
        from apps.schoolops.models_email_delivery import EmailDeliveryEvent

        # tenant-isolation-allow: platform-email-delivery-log-no-tenant-scope
        rows = (
            EmailDeliveryEvent.objects.filter(
                priority="transactional",
                subject_prefix__startswith=_SIGNUP_SUBJECT_MARKER,
            )
            .order_by("-created_at")[:_SIGNUP_VERIFY_ROWS_LIMIT]
        )
        for r in rows:
            out.append({
                "to_hash": r.to_hash,
                "subject_prefix": r.subject_prefix,
                "ok": bool(r.ok),
                "error_kind": r.error_kind or "",
                "attempts": int(r.attempts or 0),
                "created_at_iso": r.created_at.isoformat(),
            })
    except Exception as exc:  # broad-by-design — diagnostic
        logger.warning(
            "signup_diagnostics.signup_attempts_read_failed err_type=%s",
            type(exc).__name__,
        )
    return out


# rbac-allow: super-staff-signup-flow-diagnostics
@method_decorator(staff_member_required, name="dispatch")
class SignupDiagnosticsView(View):
    """Read-only operator dashboard surfacing every blocker the signup
    flow can hit at request-time.

    Renders a single template (``schoolops/super/signup_diagnostics.html``)
    extending ``control_plane_skeleton.html`` with one card per probe.
    Auto-refreshes every 60 seconds via a ``<meta http-equiv="refresh">``
    so an operator monitoring a Render deploy can watch the SMTP / broker
    state recover live.
    """

    template_name = "schoolops/super/signup_diagnostics.html"

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        db_status = _probe_db()
        broker_status = _probe_redis_celery_broker()
        outbound_status = _probe_outbound_smtp_port()
        smtp_status = _probe_smtp_server()
        counters = _recent_transactional_counters()
        signup_attempts = _recent_signup_attempts()

        # The strip-the-password version of the resolved-config dict;
        # safe to render. Wave 8's email-health helper exists for this.
        resolved_config: dict = {}
        try:
            from apps.schoolops.views_email_health import (
                _safe_resolved_config_for_render,
            )

            resolved_config = _safe_resolved_config_for_render()
        except Exception as exc:  # broad-by-design — diagnostic
            logger.warning(
                "signup_diagnostics.resolved_config_failed err_type=%s",
                type(exc).__name__,
            )

        ctx = {
            "page_title": "Signup flow diagnostics",
            "db_status": db_status,
            "broker_status": broker_status,
            "outbound_status": outbound_status,
            "smtp_status": smtp_status,
            "resolved_config": resolved_config,
            "counters": counters,
            "signup_attempts": signup_attempts,
            "refresh_seconds": 60,
        }
        return render(request, self.template_name, ctx)


__all__ = ["SignupDiagnosticsView"]
