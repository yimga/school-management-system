"""
Map backend dashboard / role-home data to decision_engine_surface.html (Phase 8).

Single builder keeps headline KPI, supporting metrics, urgent queue, next actions,
and activity aligned with apps/dashboard/role_home_engine.py declarations.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_backend_dashboard_phase7_de(
    *,
    role_home: Dict[str, Any],
    kpi_strip_cards: List[Dict[str, Any]],
    dashboard_priority_queue: List[Dict[str, Any]],
    dashboard_next_best_actions: List[Dict[str, Any]],
    role_home_primary_action: Optional[Dict[str, Any]],
    role_home_supporting_actions: List[Dict[str, Any]],
    dashboard_recent_activity: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Context keys match templates/components/decision_engine_surface.html:
    de_eyebrow, de_headline_*, de_metrics, de_urgent_queue, de_next_actions, de_activity.
    """
    cards = [c for c in (kpi_strip_cards or []) if isinstance(c, dict)]
    hero = cards[0] if cards else {}
    metrics: List[Dict[str, Any]] = []
    for c in cards[1:4]:
        metrics.append(
            {
                "label": c.get("label", ""),
                "value": c.get("value", ""),
                "meta": c.get("meta", ""),
                "status": c.get("status", "ok"),
            }
        )

    urgent: List[Dict[str, Any]] = []
    for item in dashboard_priority_queue or []:
        if not isinstance(item, dict):
            continue
        urgent.append(
            {
                "title": str(item.get("label", "") or "Item"),
                "url": str(item.get("url", "") or "") or None,
                "hint": str(item.get("meta", "") or ""),
            }
        )
    if not urgent:
        urgent.append(
            {
                "title": "Queue clear",
                "url": None,
                "hint": "No operational alerts in the current snapshot.",
            }
        )

    next_actions: List[Dict[str, Any]] = []
    if role_home_primary_action and isinstance(role_home_primary_action, dict):
        u = str(role_home_primary_action.get("url", "") or "").strip() or "#"
        next_actions.append(
            {
                "label": str(role_home_primary_action.get("label", "") or "Primary action"),
                "url": u,
            }
        )
    for step in dashboard_next_best_actions or []:
        if not isinstance(step, dict):
            continue
        lab = str(step.get("label", "") or "").strip()
        u = str(step.get("url", "") or "").strip() or "#"
        if not lab:
            continue
        if any(a.get("label") == lab and a.get("url") == u for a in next_actions):
            continue
        next_actions.append({"label": lab, "url": u})
        if len(next_actions) >= 4:
            break
    for cta in role_home_supporting_actions or []:
        if not isinstance(cta, dict):
            continue
        lab = str(cta.get("label", "") or "").strip()
        u = str(cta.get("url", "") or "").strip() or "#"
        if not lab:
            continue
        if any(a.get("label") == lab for a in next_actions):
            continue
        next_actions.append({"label": lab, "url": u})
        if len(next_actions) >= 4:
            break

    activity: List[Dict[str, Any]] = []
    for row in dashboard_recent_activity or []:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title", "") or "Activity")
        actor = str(row.get("actor", "") or "")
        act = str(row.get("action", "") or "")
        meta = " • ".join(p for p in (actor, act) if p)
        activity.append({"title": title, "meta": meta})
    if not activity:
        activity.append(
            {"title": "No recent activity", "meta": "Activity will appear as you work."}
        )

    hl_label = str(hero.get("label", "") or "Pulse")
    hl_value = hero.get("value", "—")
    hl_meta = str(hero.get("meta", "") or "")

    return {
        "eyebrow": str(role_home.get("eyebrow", "") or "Role home"),
        "headline_label": hl_label,
        "headline_value": hl_value,
        "headline_meta": hl_meta,
        "metrics": metrics,
        "urgent_queue": urgent,
        "next_actions": next_actions[:4],
        "activity": activity[:6],
    }


def build_role_home_declaration(role_home: Dict[str, Any]) -> Dict[str, Any]:
    """Structured 5-second test + audit fields (Phase 8 mandatory declaration)."""
    return {
        "dashboard_type": str(role_home.get("dashboard_type", "") or "operational"),
        "jtbd": str(role_home.get("jtbd", "") or ""),
        "main_question": str(role_home.get("main_question", "") or ""),
        "main_action": str(role_home.get("main_action", "") or ""),
    }
