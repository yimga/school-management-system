"""
D3: Setup health score. D5: Next-best-action guidance per step.
"""

from __future__ import annotations

from typing import Any

from apps.platform_runtime.role_registry import ROLE_ADMIN


def setup_health_score(school: Any, *, user: Any = None) -> dict[str, Any]:
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
        from apps.schools.runtime_assignment_evidence import runtime_assignment_evidence

        runtime_evidence = runtime_assignment_evidence(school, user=user)
        if runtime_evidence["passed"]:
            score += 25
            checks.append(("runtime", True, "Active dashboard/workflow assignment"))
        else:
            checks.append(("runtime", False, "Active dashboard/workflow assignment missing"))
        max_score += 25
        if getattr(school, "plan_id", None):
            score += 25
            checks.append(("plan", True, "Plan assigned"))
        else:
            checks.append(("plan", False, "Plan not assigned"))
        # Owner presence: a school with branding + plan + runtime but no active
        # owner has nobody who can log in, approve, or receive critical comms —
        # it is not fully set up. Query ground truth (a non-suspended owner
        # membership), the same signal the provisioning ownerless-activation
        # guard uses, so this never reads "100%" while nobody can administer it.
        max_score += 25
        from apps.schools.models import SchoolMembership

        if SchoolMembership.has_active_owner(school):
            score += 25
            checks.append(("owner", True, "Owner assigned"))
        else:
            checks.append(
                ("owner", False, "No owner assigned — assign an owner to enable login")
            )
    if max_score == 0:
        max_score = 1
    return {
        "score": round((score / max_score) * 100) if max_score else 0,
        "checks": checks,
        "max_score": max_score,
        "runtime_evidence": runtime_evidence if school else {
            "passed": False,
            "source": "none",
            "required_roles": [ROLE_ADMIN],
            "matched_roles": [],
            "counts": {},
        },
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
            if name == "owner":
                return {
                    "action": "assign_owner",
                    "label": "Assign an owner",
                    "step": 5,
                }
    return {"action": "launch", "label": "Launch checklist", "step": 8}
