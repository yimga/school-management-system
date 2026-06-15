"""
Role-home context service: single place for backend role-home orchestration.

Builds role_home, destinations, primary/supporting actions, and action registry
outputs (primary_ctas, action_chips, welcome_action_grid, quick_links, command_palette,
contextual_actions) so callers (dashboard context, accounts, etc.) get a consistent
role-home payload without duplicating logic.

RUNMYCAMPUS §6.13: Move role-home logic into services.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from apps.dashboard.action_registry import (
    get_backend_dashboard_actions,
    get_contextual_actions,
    VALID_DASHBOARD_INTENTS,
)
from apps.dashboard.role_home_engine import (
    prioritize_destinations,
    resolve_role_home,
    select_role_home_actions,
)
from apps.dashboard.north_star_guidance import build_north_star_recommended_steps
from apps.siteconfig.dashboard_pack_resolver import overlay_role_home

# Typed exceptions for pinned-order / preference reads (§2.4)
_DASHBOARD_PREFERENCE_ERRORS = (AttributeError, TypeError, ValueError, ImportError)


def build_role_home_context(
    request: Any,
    base: Dict[str, Any],
    perms: Dict[str, bool],
    *,
    safe_reverse: Callable[[str, str], str],
    build_nav_item: Callable[..., Optional[Dict[str, str]]],
    dedupe_nav_items: Callable[[List[Dict[str, str]]], List[Dict[str, str]]],
) -> Dict[str, Any]:
    """
    Build the role-home slice for the backend dashboard (and any other consumer).

    Uses role_home_engine (resolve_role_home, prioritize_destinations, select_role_home_actions)
    and action_registry (get_backend_dashboard_actions, get_contextual_actions). Applies
    finance-console injection for BURSAR/FINANCE_STAFF and pinned sidebar order from
    user preferences.

    Returns dict with: role_home, intent, primary_ctas, action_chips, welcome_action_grid,
    quick_links, command_palette, contextual_actions, role_home_destinations,
    role_home_primary_action, role_home_supporting_actions, role_home_focus_areas.
    """
    user = getattr(request, "user", None)
    role_code = (getattr(user, "role", "") or "").upper()

    intent = (base.get("dashboard_intent") or "").strip().lower()
    if intent not in VALID_DASHBOARD_INTENTS:
        intent = ""
    role_home = resolve_role_home(role_code, intent or None)
    # Dashboard Packs revival (Phase 2): overlay the school/role/user-assigned template's
    # presentation onto the role-home default. Precedence (highest first): per-user pack
    # choice → TenantLayoutAssignment → DashboardPackAssignment → role-home default. The
    # default always wins when nothing is assigned, so a new school never renders blank.
    role_home = overlay_role_home(role_home, request)
    intent = intent or role_home["default_intent"]

    actions = get_backend_dashboard_actions(
        perms, safe_reverse, build_nav_item, dedupe_nav_items, intent=intent or None
    )
    primary_ctas = actions["primary_ctas"]
    action_chips = actions["action_chips"]
    welcome_action_grid = actions["welcome_action_grid"]
    quick_links = actions["quick_links"]
    command_palette = actions["command_palette"]
    wp = (
        base.get("workflow_progress")
        if isinstance(base.get("workflow_progress"), dict)
        else None
    )
    merged_steps: list[dict] = []
    for s in build_north_star_recommended_steps(role_code, perms, workflow_progress=wp):
        merged_steps.append(s)
    raw_rec = base.get("recommended_next_steps")
    if isinstance(raw_rec, list):
        for s in raw_rec:
            if isinstance(s, dict) and s.get("action_id"):
                if not any(
                    x.get("action_id") == s.get("action_id") for x in merged_steps
                ):
                    merged_steps.append(
                        {
                            "action_id": s["action_id"],
                            "reason": s.get("reason", ""),
                            "category": s.get("category", s.get("group", "Suggested")),
                        }
                    )
    contextual_actions = get_contextual_actions(
        "backend_dashboard",
        perms,
        safe_reverse,
        intent=intent or None,
        workflow_progress=wp,
        recommended_steps=merged_steps or None,
        max_items=5,
    )

    # Finance roles: ensure Finance Console is in welcome grid if allowed
    if role_code in {"BURSAR", "FINANCE_STAFF"} and not any(
        item.get("id") == "finance_console" for item in welcome_action_grid
    ):
        finance_console = build_nav_item(
            "Finance Console",
            "bi-cash-stack",
            safe_reverse("finance:dashboard", "#"),
            item_id="finance_console",
            allow=perms.get("can_manage_finance", False),
        )
        if finance_console:
            welcome_action_grid = list(welcome_action_grid)
            welcome_action_grid.insert(0, finance_console)

    # Pinned sidebar order from user preferences
    pinned_order: List[str] = []
    try:
        prefs = getattr(user, "dashboard_preferences", None)
        if prefs and isinstance(getattr(prefs, "pinned_sidebar_items", None), list):
            pinned_order = [
                str(x).strip() for x in prefs.pinned_sidebar_items if str(x).strip()
            ]
    except _DASHBOARD_PREFERENCE_ERRORS:
        pinned_order = []
    if pinned_order:
        order_map = {key: idx for idx, key in enumerate(pinned_order)}
        quick_links = sorted(
            quick_links,
            key=lambda x: order_map.get(x.get("id", ""), 999),
        )

    role_home_destinations = prioritize_destinations(
        role_home, action_chips, quick_links, contextual_actions
    )
    quick_links = role_home_destinations[:5]

    # Next-best actions from recommended_steps or contextual_actions (for select_role_home_actions)
    recommended_steps = base.get("recommended_next_steps")
    if isinstance(recommended_steps, list):
        next_best = [
            {
                "label": s.get("label", ""),
                "url": s.get("url", "#"),
                "icon": s.get("icon", "bi-arrow-right"),
                "reason": s.get("reason", ""),
                "category": s.get("group", "Action"),
            }
            for s in recommended_steps[:3]
        ]
    else:
        next_best = [
            {
                "label": item.get("label", ""),
                "url": item.get("url", "#"),
                "icon": item.get("icon", "bi-arrow-right"),
                "reason": item.get("reason", ""),
                "category": item.get("group", "Action"),
            }
            for item in contextual_actions[:3]
        ]

    role_home_primary_action, role_home_supporting_actions = select_role_home_actions(
        next_best,
        primary_ctas,
        role_home_destinations,
    )

    return {
        "role_home": role_home,
        "intent": intent,
        "primary_ctas": primary_ctas,
        "action_chips": action_chips,
        "welcome_action_grid": welcome_action_grid,
        "quick_links": quick_links,
        "command_palette": command_palette,
        "contextual_actions": contextual_actions,
        "role_home_destinations": role_home_destinations,
        "role_home_primary_action": role_home_primary_action,
        "role_home_supporting_actions": role_home_supporting_actions,
        "role_home_focus_areas": list(role_home.get("focus_areas") or []),
        "dashboard_next_best_actions": next_best,
    }
