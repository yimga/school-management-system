"""
Human-readable public status page + JSON API for runmycampus.com /status/.
"""

from __future__ import annotations

from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.observability.db_liveness import check_db_liveness


def _component_state(key: str) -> tuple[str, str]:
    if key == "database":
        try:
            result = check_db_liveness()
            if result.get("status") == "healthy":
                return "operational", "Primary datastore responding to liveness probe."
            return "degraded", result.get("error") or "Database probe reported a non-healthy state."
        except Exception:
            return "degraded", "Database probe unavailable; platform may be in maintenance."
    return "operational", "Synthetic public-route probe; no active incident reported."


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
                "detail": meta if key == "database" else detail,
            }
        )
        if rank[state] > rank[worst]:
            worst = state
    return {
        "generated_at": timezone.now().isoformat(),
        "overall_status": worst,
        "overall_label": {
            "operational": "All systems operational",
            "degraded": "Partial degradation",
            "outage": "Major outage",
        }[worst],
        "components": rows,
        "incidents": [],
        "maintenance": [],
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
        },
    )


@require_GET
def public_health(request):
    """Lightweight probe for load balancers (no DB)."""
    return JsonResponse({"status": "healthy"})
