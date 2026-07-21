"""Frame copy + nav for /super/ operational pages (steering row parity)."""

from __future__ import annotations

from typing import Any

from apps.platform_runtime.operational_center_nav import _groups


DEFAULT_SUPER_NAV_GROUPS = _groups(
    {
        "key": "queue",
        "label": "Queue",
        "title": "Primary work visible",
        "body": "Counts, tables, and actions stay above the fold.",
    },
    {
        "key": "proof",
        "label": "Proof",
        "title": "Honest external posture",
        "body": "Blockers, PSP, and compliance remain explicit.",
    },
    {
        "key": "navigate",
        "label": "Navigate",
        "title": "Control plane links",
        "body": "Related operator surfaces stay one click away.",
    },
)

MARKETPLACE_OPS_NAV = _groups(
    {
        "key": "incidents",
        "label": "Incidents",
        "title": "Marketplace failures",
        "body": "Kill-switch and compatibility issues in one queue.",
    },
    {
        "key": "health",
        "label": "Health",
        "title": "Install health",
        "body": "Last check per active installation.",
    },
    {
        "key": "support",
        "label": "Support",
        "title": "Support dashboard",
        "body": "Full incident queue and SLA posture.",
    },
)

OBSERVABILITY_NAV = _groups(
    {
        "key": "slo",
        "label": "SLO",
        "title": "Regional SLO clocks",
        "body": "Webhook delivery and sync conflict targets.",
    },
    {
        "key": "incidents",
        "label": "Incidents",
        "title": "Platform incidents",
        "body": "Open incidents and response links.",
    },
    {
        "key": "health",
        "label": "Health",
        "title": "Control plane health",
        "body": "Runbooks and school health entry points.",
    },
)

WORKFLOW_FLIGHT_DECK_NAV = _groups(
    {
        "key": "active",
        "label": "Active",
        "title": "Running & degrading",
        "body": "Every in-flight workflow with honest ETA and step trains.",
    },
    {
        "key": "incidents",
        "label": "Incidents",
        "title": "Cross-tenant signals",
        "body": "Correlated remediation keys across tenants in the last 24h.",
    },
    {
        "key": "autopilot",
        "label": "Autopilot",
        "title": "Trusted auto-fix",
        "body": "Policies apply retry and token refresh without another click.",
    },
)

SLUG_NAV: dict[str, list[dict[str, str]]] = {
    "incident_dashboard": MARKETPLACE_OPS_NAV,
    "package_rollout": MARKETPLACE_OPS_NAV,
    "slo_dashboard": OBSERVABILITY_NAV,
    "platform_incidents": OBSERVABILITY_NAV,
    "workflow_flight_deck": WORKFLOW_FLIGHT_DECK_NAV,
}


def resolve_super_operational_frame(
    slug: str,
    *,
    center_title: str,
    center_purpose: str,
    center_eyebrow: str = "Platform operators",
    status_badge_text: str = "",
    primary_url: str = "",
    primary_label: str = "",
    secondary_url: str = "",
    secondary_label: str = "",
) -> dict[str, Any]:
    # MAX: never default to wallpaper "Operational" — omit badge unless live/descriptive.
    return {
        "page_provides_own_h1": True,
        "os_center_key": slug.replace("-", "_"),
        "center_eyebrow": center_eyebrow,
        "center_title": center_title,
        "center_purpose": center_purpose,
        "status_badge_text": status_badge_text,
        "operational_nav_groups": SLUG_NAV.get(slug, DEFAULT_SUPER_NAV_GROUPS),
        "primary_url": primary_url,
        "primary_label": primary_label,
        "secondary_url": secondary_url,
        "secondary_label": secondary_label,
    }
