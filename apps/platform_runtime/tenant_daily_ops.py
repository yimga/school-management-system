"""
Expand tenant daily ops — per-workflow next-best actions with resolved URLs.
"""

from __future__ import annotations

from typing import Any

from django.urls import NoReverseMatch, reverse

WORKFLOW_ACTIONS: dict[str, list[dict[str, Any]]] = {
    "ADMIN": [
        {"key": "attendance", "label": "Take attendance today", "url_name": "accounts:attendance_dashboard", "clicks_saved": 2},
        {"key": "announcement", "label": "Send announcement", "url_name": "communication:announcement_create", "clicks_saved": 1},
        {"key": "fees", "label": "Review unpaid invoices", "url_name": "finance:invoices", "clicks_saved": 2},
        {"key": "reports", "label": "Open reports hub", "url_name": "reports:home", "clicks_saved": 1},
    ],
    "LEADERSHIP": [
        {"key": "attendance", "label": "Attendance overview", "url_name": "accounts:attendance_dashboard", "clicks_saved": 2},
        {"key": "staff_tasks", "label": "Staff tasks", "url_name": "accounts:backend_dashboard", "clicks_saved": 1},
    ],
    "PRINCIPAL": [
        {"key": "attendance", "label": "Take attendance today", "url_name": "accounts:attendance_dashboard", "clicks_saved": 2},
        {"key": "discipline", "label": "Behavior incidents", "url_name": "people:student_list", "clicks_saved": 2},
    ],
    "TEACHER": [
        {"key": "gradebook", "label": "Open gradebook", "url_name": "evals:teacher_gradebook", "clicks_saved": 2},
        {"key": "attendance", "label": "Mark attendance", "url_name": "accounts:attendance_dashboard", "clicks_saved": 1},
        {"key": "assignments", "label": "Post assignment", "url_name": "evals:assignment_create", "clicks_saved": 2},
    ],
    "PARENT": [
        {"key": "messages", "label": "Message school", "url_name": "communication:parent_inbox", "clicks_saved": 1},
        {"key": "fees", "label": "Pay fees", "url_name": "finance:parent_payments", "clicks_saved": 2},
        {"key": "student360", "label": "Student overview", "url_name": "student360:parent_dashboard", "clicks_saved": 1},
    ],
    "STUDENT": [
        {"key": "assignments", "label": "My assignments", "url_name": "evals:student_assignments", "clicks_saved": 1},
    ],
}


def next_best_actions_for_role(school, user) -> list[dict[str, Any]]:
    role = (getattr(user, "role", "") or "").upper()
    actions = list(WORKFLOW_ACTIONS.get(role, WORKFLOW_ACTIONS.get("ADMIN", [])))
    sid = str(getattr(school, "pk", "") or "")
    for action in actions:
        action["school_id"] = sid
        action["workflow"] = action.get("key", "")
    return actions


def resolve_action_urls(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for action in actions:
        row = dict(action)
        url_name = row.pop("url_name", "")
        row["url"] = ""
        if url_name:
            try:
                row["url"] = reverse(url_name)
            except NoReverseMatch:
                row["url"] = ""
        resolved.append(row)
    return resolved
