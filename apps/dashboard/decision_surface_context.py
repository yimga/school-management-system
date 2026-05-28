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
    max_next_actions: int = 4,
    role_home_destinations: Optional[List[Dict[str, Any]]] = None,
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
    _cap = min(4, max(1, int(max_next_actions or 4)))
    if role_home_primary_action and isinstance(role_home_primary_action, dict):
        u = str(role_home_primary_action.get("url", "") or "").strip() or "#"
        next_actions.append(
            {
                "label": str(role_home_primary_action.get("label", "") or "Primary action"),
                "url": u,
            }
        )
    for step in dashboard_next_best_actions or []:
        if len(next_actions) >= _cap:
            break
        if not isinstance(step, dict):
            continue
        lab = str(step.get("label", "") or "").strip()
        u = str(step.get("url", "") or "").strip() or "#"
        if not lab:
            continue
        if any(a.get("label") == lab and a.get("url") == u for a in next_actions):
            continue
        next_actions.append({"label": lab, "url": u})
        if len(next_actions) >= _cap:
            break
    for cta in role_home_supporting_actions or []:
        if len(next_actions) >= _cap:
            break
        if not isinstance(cta, dict):
            continue
        lab = str(cta.get("label", "") or "").strip()
        u = str(cta.get("url", "") or "").strip() or "#"
        if not lab:
            continue
        if any(a.get("label") == lab for a in next_actions):
            continue
        next_actions.append({"label": lab, "url": u})
        if len(next_actions) >= _cap:
            break

    if not next_actions:
        for item in role_home_destinations or []:
            if not isinstance(item, dict):
                continue
            lab = str(item.get("label", "") or "").strip()
            u = str(item.get("url", "") or "").strip() or "#"
            if lab:
                next_actions.append({"label": lab, "url": u})
                break
    if not next_actions:
        mj = str(role_home.get("main_action", "") or "").strip() or "Continue"
        next_actions.append({"label": mj[:160], "url": "#"})

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
        "next_actions": next_actions[:_cap],
        "activity": activity[:6],
    }


def build_teacher_dashboard_phase7_de(
    *,
    pending_evaluations: int = 0,
    completion_pct: int = 0,
    attendance_pct: int | None = None,
    teacher_fast_workflows: list[dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Decision surface for teacher role-home (marks + attendance at a glance)."""
    from django.urls import reverse

    def _rev(name: str, fallback: str = "#") -> str:
        try:
            return reverse(name)
        except Exception:  # noqa: BLE001
            return fallback

    kpi_strip: List[Dict[str, Any]] = [
        {
            "label": "Marks pending",
            "value": pending_evaluations,
            "meta": "evaluations due",
            "status": "danger" if pending_evaluations else "ok",
        },
        {
            "label": "Grading complete",
            "value": f"{completion_pct}%",
            "meta": "this term",
            "status": "ok" if completion_pct >= 75 else "warn",
        },
    ]
    if attendance_pct is not None:
        kpi_strip.append(
            {
                "label": "Attendance",
                "value": f"{attendance_pct}%",
                "meta": "class average",
                "status": "ok" if attendance_pct >= 85 else "warn",
            }
        )

    urgent: List[Dict[str, Any]] = []
    if pending_evaluations > 0:
        urgent.append(
            {
                "title": f"{pending_evaluations} mark entries pending",
                "url": _rev("evals:teacher_marks_entry"),
                "hint": "Enter scores while context is fresh.",
            }
        )
    else:
        urgent.append(
            {
                "title": "Marks queue clear",
                "url": None,
                "hint": "No pending evaluations in the current snapshot.",
            }
        )

    next_actions: List[Dict[str, Any]] = []
    for row in teacher_fast_workflows or []:
        if not isinstance(row, dict):
            continue
        lab = str(row.get("label", "") or "").strip()
        url = str(row.get("url", "") or "").strip()
        if lab and url:
            next_actions.append({"label": lab, "url": url})
        if len(next_actions) >= 4:
            break
    if not next_actions:
        next_actions.append(
            {
                "label": "Enter marks",
                "url": _rev("evals:teacher_marks_entry"),
            }
        )

    role_home = {
        "eyebrow": "Teacher home",
        "purpose": "Teaching day at a glance",
        "dashboard_type": "role-home",
        "jtbd": "Complete marks and attendance with minimal navigation.",
        "main_question": "What needs my attention in class today?",
        "main_action": "Enter marks",
    }
    return build_backend_dashboard_phase7_de(
        role_home=role_home,
        kpi_strip_cards=kpi_strip,
        dashboard_priority_queue=urgent,
        dashboard_next_best_actions=next_actions,
        role_home_primary_action=next_actions[0] if next_actions else None,
        role_home_supporting_actions=next_actions[1:4],
        dashboard_recent_activity=[
            {
                "title": "Teaching workspace ready",
                "actor": "System",
                "action": "prepared your dashboard",
                "time_ago": "just now",
            }
        ],
    )


def build_role_home_declaration(role_home: Dict[str, Any]) -> Dict[str, Any]:
    """Structured 5-second test + audit fields (Phase 8 mandatory declaration)."""
    return {
        "dashboard_type": str(role_home.get("dashboard_type", "") or "operational"),
        "jtbd": str(role_home.get("jtbd", "") or ""),
        "main_question": str(role_home.get("main_question", "") or ""),
        "main_action": str(role_home.get("main_action", "") or ""),
    }
