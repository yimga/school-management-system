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
    action_id: str = "",
    score: int = 50,
) -> None:
    if not url or url == "#":
        return
    if any(
        item["label"] == label
        or item["url"] == url
        or (action_id and item.get("action_id") == action_id)
        for item in steps
    ):
        return
    steps.append(
        {
            "label": label,
            "url": url,
            "icon": icon,
            "reason": reason,
            "category": category,
            "action_id": action_id,
            "score": score,
        }
    )


def get_recommended_next_steps(
    workflow_progress: Dict[str, Any],
    *,
    year=None,
    intent: str | None = None,
    priority_signals: Dict[str, Any] | None = None,
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
    signals = priority_signals or {}
    overdue_invoices = int(signals.get("overdue_invoices", 0) or 0)
    pending_approvals = int(signals.get("pending_approvals_count", 0) or 0)
    pending_invites = int(signals.get("pending_invites", 0) or 0)
    at_risk_students = int(signals.get("at_risk_students", 0) or 0)
    draft_invoices = int(signals.get("draft_invoices", 0) or 0)

    if not active_year_ready:
        _append_step(
            steps,
            label="Open Setup Studio",
            url=_safe_reverse("siteconfig:guided_onboarding", _safe_reverse("accounts:workflow_center")),
            icon="bi-magic",
            reason="Academic year, blueprint, and launch readiness still need one guided setup surface.",
            category="Setup",
            action_id="setup_studio",
            score=100 if resolved_intent == "setup" else 94,
        )

    if students == 0:
        _append_step(
            steps,
            label="Add student roster",
            url=_safe_reverse("accounts:backend_student_create", _safe_reverse("admin:index")),
            icon="bi-person-plus",
            reason="Admissions, attendance, finance, and family workflows need active student records.",
            category="People",
            action_id="add_student",
            score=96 if resolved_intent in {"setup", "operational"} else 90,
        )

    if teachers == 0:
        _append_step(
            steps,
            label="Add teacher coverage",
            url=_safe_reverse("accounts:backend_teacher_create", _safe_reverse("admin:index")),
            icon="bi-person-badge",
            reason="Academic delivery and parent communication are incomplete without staff coverage.",
            category="People",
            action_id="add_teacher",
            score=95 if resolved_intent in {"setup", "academic"} else 88,
        )

    if classrooms == 0:
        _append_step(
            steps,
            label="Open workflow center",
            url=_safe_reverse("accounts:workflow_center"),
            icon="bi-diagram-3",
            reason="Classrooms, approvals, and launch tasks converge fastest in the workflow queue.",
            category="Setup",
            action_id="workflow_center",
            score=92 if resolved_intent in {"setup", "operational"} else 84,
        )

    if overdue_invoices > 0 or draft_invoices > 0 or resolved_intent == "finance":
        _append_step(
            steps,
            label="Review collections",
            url=_safe_reverse("finance:dashboard"),
            icon="bi-cash-stack",
            reason="Collections, overdue invoices, and draft billing items need an explicit finance-first pass.",
            category="Finance",
            action_id="finance_console",
            score=98 if overdue_invoices > 0 else 90,
        )

    if pending_approvals > 0 or pending_invites > 0 or resolved_intent in {"operational", "executive"}:
        _append_step(
            steps,
            label="Resolve active queues",
            url=_safe_reverse("accounts:workflow_center"),
            icon="bi-diagram-3",
            reason="Approvals, invites, and operational blockers should be cleared from one queue-first surface.",
            category="Operations",
            action_id="workflow_center",
            score=97 if pending_approvals > 0 else 89,
        )

    if at_risk_students > 0 or resolved_intent == "academic":
        _append_step(
            steps,
            label="Review grading and interventions",
            url=_safe_reverse("reports:publish_term_results", _safe_reverse("accounts:workflow_center")),
            icon="bi-journal-check",
            reason="Academic risk, report readiness, and intervention timing should stay in one academic workbench.",
            category="Academic",
            action_id="manage_exams",
            score=95 if at_risk_students > 0 else 86,
        )

    if resolved_intent == "setup":
        _append_step(
            steps,
            label="Open Setup Studio",
            url=_safe_reverse("siteconfig:guided_onboarding", _safe_reverse("accounts:backend_dashboard")),
            icon="bi-magic",
            reason="Keep setup, launch blockers, previews, and blueprint decisions in one guided operator flow.",
            category="Setup",
            action_id="setup_studio",
            score=93,
        )
    elif resolved_intent == "executive":
        _append_step(
            steps,
            label="Review school pulse",
            url=_safe_reverse("accounts:workflow_center"),
            icon="bi-speedometer2",
            reason="Executive mode should start from decisions, blockers, and the operating pulse.",
            category="Executive",
            action_id="workflow_center",
            score=88,
        )

    _append_step(
        steps,
        label="Open command center",
        url=_safe_reverse("accounts:backend_dashboard"),
        icon="bi-command",
        reason="Search and commands should replace sidebar hunting for major tasks.",
        category="Navigation",
        score=40,
    )

    steps.sort(key=lambda item: int(item.get("score", 0)), reverse=True)
    sliced = steps[:max_steps]
    for index, item in enumerate(sliced):
        item["priority"] = "now" if index == 0 else "next" if index < 3 else "later"
        item.pop("score", None)
    return sliced
