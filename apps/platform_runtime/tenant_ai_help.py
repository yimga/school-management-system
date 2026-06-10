"""
Tenant-safe AI help routing — online/offline posture without cross-tenant leakage.
"""

from __future__ import annotations

from typing import Any

from django.urls import NoReverseMatch, reverse


def build_tenant_ai_help_context(request, *, route_name: str = "") -> dict[str, Any]:
    """
    Ground help instructions in named routes and tenant flags — no hallucinated buttons.
    """
    from apps.portal.help_governance import ai_help_enabled_for_request
    from services.ai_helpers import is_ai_available

    school = getattr(request, "school", None)
    online = bool(ai_help_enabled_for_request(request))
    ai_up = is_ai_available(school) if school else False
    breadcrumbs: list[dict[str, str]] = []
    resolved_route = route_name or getattr(getattr(request, "resolver_match", None), "view_name", "") or ""
    if resolved_route:
        breadcrumbs.append({"kind": "route", "value": resolved_route})

    help_url = ""
    try:
        help_url = reverse("feedback:help_center")
    except NoReverseMatch:
        help_url = "/help/"

    if online and resolved_route:
        help_url = f"{help_url}?focus={resolved_route}"

    return {
        "online_mode": online,
        "ai_available": ai_up,
        "offline_mode": not online or not ai_up,
        "tenant_id_hash": str(getattr(school, "tenant_hash", "") or "")[:12],
        "route_name": resolved_route,
        "breadcrumbs": breadcrumbs,
        "help_center_url": help_url,
        "deterministic_fallback": not ai_up,
        "tenant_safe_message": (
            "AI help is temporarily unavailable. Use the Help Center articles below."
            if not ai_up
            else "Ask a setup or operations question — answers stay within your school."
        ),
    }


def offline_help_actions() -> list[dict[str, str]]:
    """Actions safe when cloud AI is unavailable."""
    from apps.sync_engine.offline_help import offline_help_queue_contract

    contract = offline_help_queue_contract()
    return [
        {
            "action": "search_help_center",
            "label": "Search Help Center (works offline for cached articles)",
        },
        {
            "action": "queue_for_sync",
            "label": "Save draft — syncs when you reconnect",
            "sync_backend": contract["queue_backend"],
        },
    ]
