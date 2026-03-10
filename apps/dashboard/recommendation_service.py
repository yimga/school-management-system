"""
Recommendation service: single source for recommended next steps on dashboards.
Used by backend dashboard, control plane, and other role homes.
Returns outcome-first, short lists (top 3–5) based on workflow progress and context.
"""
from __future__ import annotations

from typing import Any, Dict, List

from django.urls import NoReverseMatch, reverse


def _safe_reverse(name: str, fallback: str = "#") -> str:
    try:
        return reverse(name)
    except NoReverseMatch:
        return fallback
    except Exception:
        return fallback


def get_recommended_next_steps(
    workflow_progress: Dict[str, Any],
    *,
    year=None,
    intent: str | None = None,
    max_steps: int = 5,
) -> List[Dict[str, str]]:
    """
    Build recommended next steps for backend/operator dashboards.

    Args:
        workflow_progress: dict with keys classrooms, students, teachers (counts).
        year: active academic year or None.
        intent: optional dashboard intent (executive, operational, academic, finance, setup).
        max_steps: maximum number of steps to return.

    Returns:
        List of {"label", "url", "icon"} dicts, ordered by priority.
    """
    steps: List[Dict[str, str]] = []
    has_year = bool(year)

    try:
        if not has_year:
            steps.append({
                "label": "Set up academic year",
                "url": _safe_reverse("accounts:workflow_center"),
                "icon": "bi-calendar-event",
            })
        else:
            if workflow_progress.get("classrooms", 0) == 0:
                steps.append({
                    "label": "Create classrooms",
                    "url": _safe_reverse("accounts:workflow_center"),
                    "icon": "bi-door-open",
                })
            if workflow_progress.get("students", 0) == 0:
                url = _safe_reverse("accounts:backend_student_create")
                if url == "#":
                    url = _safe_reverse("admin:index")
                steps.append({"label": "Add student", "url": url, "icon": "bi-person-plus"})
            if workflow_progress.get("teachers", 0) == 0:
                url = _safe_reverse("accounts:backend_teacher_create")
                if url == "#":
                    url = _safe_reverse("admin:index")
                steps.append({"label": "Add teacher", "url": url, "icon": "bi-person-badge"})
        if not steps:
            steps.append({
                "label": "Workflow Center",
                "url": _safe_reverse("accounts:workflow_center"),
                "icon": "bi-diagram-3",
            })
            steps.append({
                "label": "Publish results",
                "url": _safe_reverse("reports:publish_term_results"),
                "icon": "bi-award",
            })
    except Exception:
        steps = [{
            "label": "Workflow Center",
            "url": _safe_reverse("accounts:workflow_center"),
            "icon": "bi-diagram-3",
        }]

    return steps[:max_steps]
