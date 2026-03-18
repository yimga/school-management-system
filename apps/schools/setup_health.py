"""
D3: Setup health score. D5: Next-best-action guidance per step.
"""

from __future__ import annotations

from typing import Any


def setup_health_score(school: Any) -> dict[str, Any]:
    """
    Return a simple health score (0-100) and checklist for school setup.
    Used by Setup Studio and admin.
    """
    score = 0
    max_score = 0
    checks = []
    if school:
        max_score += 25
        if getattr(school, "name", None) and getattr(school, "slug", None):
            score += 25
            checks.append(("school_created", True, "School created"))
        else:
            checks.append(("school_created", False, "School not created"))
        max_score += 25
        if getattr(school, "theme_pack_id", None) or getattr(
            school, "primary_color", None
        ):
            score += 25
            checks.append(("branding", True, "Branding set"))
        else:
            checks.append(("branding", False, "Branding not set"))
        max_score += 25
        if getattr(school, "default_dashboard_slug", None) or getattr(
            school, "default_workflow_slug", None
        ):
            score += 25
            checks.append(("runtime", True, "Dashboard/workflow assigned"))
        else:
            checks.append(("runtime", False, "Dashboard/workflow not assigned"))
        max_score += 25
        if getattr(school, "plan_id", None):
            score += 25
            checks.append(("plan", True, "Plan assigned"))
        else:
            checks.append(("plan", False, "Plan not assigned"))
    if max_score == 0:
        max_score = 1
    return {
        "score": round((score / max_score) * 100) if max_score else 0,
        "checks": checks,
        "max_score": max_score,
    }


def next_best_action(school: Any, step: int | None = None) -> dict[str, Any]:
    """
    D5: Return suggested next step for Setup Studio (outcome-first).
    """
    health = setup_health_score(school)
    if not school:
        return {"action": "create_school", "label": "Create school", "step": 1}
    for name, passed, label in health["checks"]:
        if not passed:
            if name == "school_created":
                return {
                    "action": "complete_school",
                    "label": "Complete school details",
                    "step": 1,
                }
            if name == "plan":
                return {"action": "assign_plan", "label": "Assign plan", "step": 2}
            if name == "branding":
                return {
                    "action": "configure_branding",
                    "label": "Configure branding",
                    "step": 3,
                }
            if name == "runtime":
                return {
                    "action": "assign_dashboard",
                    "label": "Assign dashboard/workflow",
                    "step": 4,
                }
    return {"action": "launch", "label": "Launch checklist", "step": 8}
