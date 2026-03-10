"""
Recommendation service: single source for recommended next steps on dashboards.
Used by backend dashboard, control plane, and other role homes.
Returns short, outcome-first lists based on workflow state and dashboard intent.
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


def _append_step(
    steps: List[Dict[str, str]],
    *,
    label: str,
    url: str,
    icon: str,
    reason: str,
    category: str,
) -> None:
    if not url or url == "#":
        return
    if any(item["label"] == label or item["url"] == url for item in steps):
        return
    steps.append(
        {
            "label": label,
            "url": url,
            "icon": icon,
            "reason": reason,
            "category": category,
        }
    )


def get_recommended_next_steps(
    workflow_progress: Dict[str, Any],
    *,
    year=None,
    intent: str | None = None,
    max_steps: int = 5,
) -> List[Dict[str, str]]:
    """
    Build recommended next steps for backend/operator dashboards.

    Returns:
        List of {"label", "url", "icon", "reason", "category"} dicts, ordered by priority.
    """
    steps: List[Dict[str, str]] = []
    classrooms = int(workflow_progress.get("classrooms", 0) or 0)
    students = int(workflow_progress.get("students", 0) or 0)
    teachers = int(workflow_progress.get("teachers", 0) or 0)
    active_year_ready = bool(year)
    resolved_intent = (intent or "").strip().lower()

    if not active_year_ready:
        _append_step(
            steps,
            label="Set up academic year",
            url=_safe_reverse("accounts:workflow_center"),
            icon="bi-calendar-event",
            reason="Most downstream workflows stay blocked until the active year exists.",
            category="Setup",
        )

    if students == 0:
        _append_step(
            steps,
            label="Add student roster",
            url=_safe_reverse("accounts:backend_student_create", _safe_reverse("admin:index")),
            icon="bi-person-plus",
            reason="Admissions, attendance, finance, and family workflows need active student records.",
            category="People",
        )

    if teachers == 0:
        _append_step(
            steps,
            label="Add teacher coverage",
            url=_safe_reverse("accounts:backend_teacher_create", _safe_reverse("admin:index")),
            icon="bi-person-badge",
            reason="Academic delivery and parent communication are incomplete without staff coverage.",
            category="People",
        )

    if classrooms == 0:
        _append_step(
            steps,
            label="Create classrooms",
            url=_safe_reverse("accounts:workflow_center"),
            icon="bi-door-open",
            reason="Classrooms turn imported people and timetable data into usable operations.",
            category="Setup",
        )

    if resolved_intent == "setup":
        _append_step(
            steps,
            label="Open Setup Studio",
            url=_safe_reverse("siteconfig:guided_onboarding", _safe_reverse("accounts:backend_dashboard")),
            icon="bi-magic",
            reason="Finish blueprint, branding, and launch-readiness tasks from one guided surface.",
            category="Setup",
        )
    elif resolved_intent == "finance":
        _append_step(
            steps,
            label="Review collections",
            url=_safe_reverse("finance:dashboard"),
            icon="bi-cash-stack",
            reason="Finance mode should open cash collection and approval decisions first.",
            category="Finance",
        )
    elif resolved_intent == "academic":
        _append_step(
            steps,
            label="Review grading and reports",
            url=_safe_reverse("reports:publish_term_results", _safe_reverse("accounts:workflow_center")),
            icon="bi-journal-check",
            reason="Academic mode is for outcomes, interventions, and publishing readiness.",
            category="Academic",
        )
    elif resolved_intent == "executive":
        _append_step(
            steps,
            label="Open decision queue",
            url=_safe_reverse("accounts:workflow_center"),
            icon="bi-speedometer2",
            reason="Executive mode should surface the shortest path to decisions and blockers.",
            category="Executive",
        )
    else:
        _append_step(
            steps,
            label="Open workflow center",
            url=_safe_reverse("accounts:workflow_center"),
            icon="bi-diagram-3",
            reason="Workflow Center remains the fastest route when multiple queues need attention.",
            category="Operations",
        )

    _append_step(
        steps,
        label="Open command center",
        url=_safe_reverse("accounts:backend_dashboard"),
        icon="bi-command",
        reason="Search and commands should replace sidebar hunting for major tasks.",
        category="Navigation",
    )

    _append_step(
        steps,
        label="Review finance health",
        url=_safe_reverse("finance:dashboard", _safe_reverse("accounts:backend_dashboard")),
        icon="bi-wallet2",
        reason="Operational readiness is not complete until collections and invoices are in good shape.",
        category="Finance",
    )

    return steps[:max_steps]
