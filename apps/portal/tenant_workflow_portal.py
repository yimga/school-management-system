"""Shared tenant workflow portal payloads for parent, teacher, and student."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User


def _safe_reverse(name: str) -> str:
    try:
        return reverse(name)
    except (NoReverseMatch, AttributeError, TypeError, ValueError):
        return ""


def _clean_title(title: str) -> str:
    value = str(title or "").strip()
    if ") " in value[:5]:
        return value.split(") ", 1)[1]
    return value


def _step_done(step: dict[str, Any]) -> bool:
    if "done" in step:
        return bool(step.get("done"))
    label = str(step.get("progress_label") or "").lower()
    negative_tokens = (
        "no ",
        "not ",
        "pending",
        "access not",
        "link a",
        "request access",
    )
    return bool(label) and not any(token in label for token in negative_tokens)


def _role_copy(role: str) -> dict[str, str]:
    role_upper = (role or "").upper()
    if role_upper == User.Role.TEACHER:
        return {
            "eyebrow": str(_("Teacher workflow")),
            "title": str(_("My teaching day")),
            "subtitle": str(_("Attendance, marks, syllabus, messages, and personal admin in one focused path.")),
            "home_label": str(_("Teacher hub")),
            "home_url": _safe_reverse("portal:teacher_dashboard_alias"),
            "default_action": str(_("Open teacher hub")),
        }
    if role_upper == User.Role.STUDENT:
        return {
            "eyebrow": str(_("Student workflow")),
            "title": str(_("My learning path")),
            "subtitle": str(_("Messages, syllabus, timetable, profile, and help in one simple student checklist.")),
            "home_label": str(_("Student home")),
            "home_url": _safe_reverse("portal:student_portal_grades"),
            "default_action": str(_("Open student home")),
        }
    return {
        "eyebrow": str(_("Family workflow")),
        "title": str(_("My family path")),
        "subtitle": str(_("Children, results, attendance, finance, documents, and school contact in one calm checklist.")),
        "home_label": str(_("Family home")),
        "home_url": _safe_reverse("portal:parent_dashboard"),
        "default_action": str(_("Open family home")),
    }


def _metric(label: str, value: Any, tone: str = "neutral") -> dict[str, str]:
    return {"label": str(label), "value": str(value), "tone": tone}


def _metrics_for_role(role: str, progress: dict[str, Any], done: int, total: int) -> list[dict[str, str]]:
    role_upper = (role or "").upper()
    completion = int(round((done / total) * 100)) if total else 0
    metrics = [_metric(_("Workflow ready"), f"{completion}%", "success" if completion >= 80 else "warning")]
    if role_upper == User.Role.TEACHER:
        metrics.extend(
            [
                _metric(_("Classes"), progress.get("assignments", 0)),
                _metric(_("Marks"), f"{progress.get('completion_pct', 0)}%"),
                _metric(_("Pending"), progress.get("pending_marks", 0), "warning" if progress.get("pending_marks") else "success"),
            ]
        )
    elif role_upper == User.Role.STUDENT:
        metrics.extend(
            [
                _metric(_("Messages"), progress.get("unread_messages", 0), "warning" if progress.get("unread_messages") else "success"),
                _metric(_("Profile"), progress.get("profile_state", _("Ready"))),
                _metric(_("Resources"), progress.get("resource_count", 0)),
            ]
        )
    else:
        metrics.extend(
            [
                _metric(_("Children"), progress.get("children_linked", 0)),
                _metric(_("Attendance"), f"{progress.get('attendance_pct', 0)}%"),
                _metric(_("Finance"), progress.get("finance_balance", 0), "warning" if progress.get("finance_overdue") else "success"),
            ]
        )
    return metrics[:4]


def build_tenant_workflow_portal(
    request: HttpRequest,
    *,
    role: str,
    steps: list[dict[str, Any]],
    workflow_progress: dict[str, Any] | None = None,
    active_year: Any = None,
    active_term: Any = None,
    empty_state: bool = False,
) -> dict[str, Any]:
    """Normalize role workflow data into one premium tenant workflow shape."""
    progress = workflow_progress or {}
    normalized_steps: list[dict[str, Any]] = []
    for index, step in enumerate(steps or [], start=1):
        row = dict(step)
        row["title_clean"] = _clean_title(str(row.get("title") or ""))
        row["step_index"] = row.get("step_index") or index
        row["total_steps"] = row.get("total_steps") or len(steps or [])
        row["done"] = _step_done(row)
        row["status_label"] = str(_("Done")) if row["done"] else str(_("Next"))
        row["links"] = [link for link in row.get("links") or [] if link and link.get("url")]
        normalized_steps.append(row)

    total = len(normalized_steps)
    done = sum(1 for step in normalized_steps if step["done"])
    focus = next((step for step in normalized_steps if not step["done"]), normalized_steps[0] if normalized_steps else {})
    focus_links = focus.get("links") or []
    copy = _role_copy(role)
    primary_action = (
        focus_links[0]
        if focus_links
        else {"label": copy["default_action"], "url": copy["home_url"]}
    )
    secondary_actions = []
    for step in normalized_steps:
        for link in step.get("links") or []:
            if link.get("url") != primary_action.get("url"):
                secondary_actions.append(link)
            if len(secondary_actions) >= 4:
                break
        if len(secondary_actions) >= 4:
            break

    return {
        **copy,
        "role": (role or "").upper(),
        "steps": normalized_steps,
        "focus": focus,
        "done_steps": done,
        "total_steps": total,
        "completion_pct": int(round((done / total) * 100)) if total else 0,
        "metrics": _metrics_for_role(role, progress, done, total),
        "primary_action": primary_action,
        "secondary_actions": secondary_actions,
        "active_year_label": getattr(active_year, "name", None) or str(active_year or ""),
        "active_term_label": getattr(active_term, "label", None) or str(active_term or ""),
        "empty_state": bool(empty_state),
        "help_url": _safe_reverse("feedback:help_center"),
        "feedback_url": _safe_reverse("feedback:school_feedback"),
    }
