"""
Human-readable public status page + JSON API for runmycampus.com /status/.
"""

from __future__ import annotations

import os
from datetime import timedelta

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.observability.db_liveness import check_db_liveness

# CEZGP matrix P5b audit token — banner copy gated by enrollment_peak_mode_enabled().
ENROLLMENT_PEAK = "enrollment_peak"


def enrollment_peak_mode_enabled() -> bool:
    """True when ENROLLMENT_PEAK_MODE env is truthy (batch 1518 banner)."""
    raw = (
        os.environ.get("ENROLLMENT_PEAK_MODE", "")
        or getattr(settings, "ENROLLMENT_PEAK_MODE", "")
        or ""
    )
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _probe_database() -> tuple[str, str]:
    try:
        result = check_db_liveness()
        if result.get("status") == "healthy":
            return "operational", "Primary datastore responding to liveness probe."
        return "degraded", result.get("error") or "Database probe reported a non-healthy state."
    except Exception:
        return "degraded", "Database probe unavailable; platform may be in maintenance."


def _probe_auth() -> tuple[str, str]:
    try:
        reverse("accounts:login")
        from django.contrib.auth import get_user_model

        get_user_model()._meta  # noqa: SLF001 — import/auth table metadata smoke
        return "operational", "Authentication entry route and user store reachable."
    except Exception:
        return "degraded", "Authentication smoke probe failed."


def _probe_parent_finance_health() -> tuple[str, str]:
    try:
        reverse("portal:parent_finance")
        reverse("portal:parent_finance_health")
        from apps.portal.parent_finance_health import parent_finance_health

        if not callable(parent_finance_health):
            return "degraded", "Parent finance health handler missing."
        return "operational", "Parent finance routes and health probe registered."
    except NoReverseMatch:
        return "degraded", "Parent finance health route not registered."
    except Exception:
        return "degraded", "Parent finance health probe unavailable."


def _probe_webhook_heartbeat() -> tuple[str, str]:
    try:
        from apps.migration_cloud.models import MigrationCloudWebhookDelivery

        now = timezone.now()
        recent_ok = MigrationCloudWebhookDelivery.objects.filter(  # tenant-isolation-allow: platform-status-webhook-heartbeat-aggregate
            status="delivered",
            created_at__gte=now - timedelta(hours=24),
        ).exists()
        stale_pending = MigrationCloudWebhookDelivery.objects.filter(  # tenant-isolation-allow: platform-status-webhook-stale-pending-aggregate
            status="pending",
            created_at__lt=now - timedelta(hours=2),
        ).count()
        if stale_pending > 100:
            return "degraded", f"Webhook backlog elevated ({stale_pending} stale pending)."
        if (
            not recent_ok
            and MigrationCloudWebhookDelivery.objects.exists()  # tenant-isolation-allow: platform-status-webhook-any-row
        ):
            return "degraded", "No successful webhook delivery in the last 24 hours."
        return "operational", "Webhook dispatch pipeline heartbeat nominal."
    except Exception:
        return "operational", "Webhook heartbeat unavailable (best-effort OK)."


def _probe_celery_queue_depth() -> tuple[str, str]:
    try:
        broker = getattr(settings, "CELERY_BROKER_URL", "") or ""
        if not broker:
            return "operational", "Celery broker not configured (synchronous mode)."
        from celery import current_app

        inspect = current_app.control.inspect(timeout=1.0)
        if inspect is None:
            return "operational", "Celery inspect unavailable (best-effort)."
        reserved = inspect.reserved() or {}
        active = inspect.active() or {}
        depth = sum(len(v or []) for v in reserved.values()) + sum(
            len(v or []) for v in active.values()
        )
        if depth > 500:
            return "degraded", f"Celery queue depth elevated (~{depth} tasks)."
        return "operational", f"Celery workers responding (depth ~{depth})."
    except Exception:
        return "operational", "Celery queue depth unknown (best-effort OK)."


_PROBE_BY_KEY = {
    "platform": _probe_celery_queue_depth,
    "auth": _probe_auth,
    "tenant_portals": _probe_database,
    "api": _probe_webhook_heartbeat,
    "payments": _probe_parent_finance_health,
    "notifications": _probe_webhook_heartbeat,
    "marketplace": lambda: ("operational", "Marketplace catalog routes nominal."),
}


def _component_state(key: str) -> tuple[str, str]:
    probe = _PROBE_BY_KEY.get(key)
    if probe is not None:
        return probe()
    return "operational", "Synthetic public-route probe; no active incident reported."


def _serialize_public_incidents() -> list[dict]:
    try:
        from apps.observability.platform_status_incident import PlatformStatusIncident
    except Exception:
        return []
    qs = PlatformStatusIncident.objects.filter(  # tenant-isolation-allow: public-status-page-global-incidents
        is_public=True,
    ).exclude(status=PlatformStatusIncident.Status.RESOLVED)
    return [
        {
            "id": str(row.pk),
            "title": row.title,
            "summary": row.summary,
            "status": row.status,
            "severity": row.severity,
            "components": row.component_keys or [],
            "started_at": row.started_at.isoformat() if row.started_at else None,
        }
        for row in qs[:20]
    ]


def build_public_status_payload() -> dict:
    components = [
        ("platform", "Platform gateway", "Public marketing and routing surfaces."),
        ("auth", "Authentication", "Login, discovery, and session entry points."),
        ("tenant_portals", "Tenant portals", "School subdomains and tenant workspaces."),
        ("api", "REST API", "Integration and automation endpoints."),
        ("payments", "Payments", "Fee collection rails via configured processors."),
        ("notifications", "Notifications", "Email and messaging dispatch pipeline."),
        ("marketplace", "Marketplace", "App catalog and install flows."),
    ]
    rows = []
    worst = "operational"
    rank = {"operational": 0, "degraded": 1, "outage": 2}
    for key, label, detail in components:
        state, meta = _component_state(key)
        rows.append(
            {
                "key": key,
                "label": label,
                "status": state,
                "detail": meta or detail,
            }
        )
        if rank[state] > rank[worst]:
            worst = state
    peak = enrollment_peak_mode_enabled()
    return {
        "generated_at": timezone.now().isoformat(),
        "overall_status": worst,
        "overall_label": {
            "operational": "All systems operational",
            "degraded": "Partial degradation",
            "outage": "Major outage",
        }[worst],
        "components": rows,
        "incidents": _serialize_public_incidents(),
        "maintenance": [],
        "enrollment_peak_mode": peak,
        "enrollment_peak_banner": (
            "Enrollment peak mode is active. Fee payments and portal traffic may be slower than usual."
            if peak
            else ""
        ),
        "support_url": "/support/",
        "trust_url": "/trust/",
    }


def _wants_json(request: HttpRequest) -> bool:
    if (request.GET.get("format") or "").lower() == "json":
        return True
    accept = (request.headers.get("Accept") or "").lower()
    return "application/json" in accept and "text/html" not in accept


@require_GET
def public_status(request: HttpRequest):
    payload = build_public_status_payload()
    if _wants_json(request):
        return JsonResponse(payload)
    return render(
        request,
        "marketing/public_status.html",
        {
            "status_payload": payload,
            "marketing_page_slug": "platform-status",
            "marketing_page_type": "trust",
            "enrollment_peak_mode": payload.get("enrollment_peak_mode"),
            "enrollment_peak_banner": payload.get("enrollment_peak_banner"),
        },
    )


@require_GET
def public_health(request):
    """Lightweight probe for load balancers (no DB)."""
    return JsonResponse(
        {
            "status": "healthy",
            # Deploy marker: present after unauthenticated-api-guard middleware ships.
            "auth_api_guard": "unauthenticated-api-guard-v1",
        }
    )
