"""
Expand tenant daily ops — per-workflow next-best actions with resolved URLs.
"""

from __future__ import annotations

import logging
from typing import Any

from django.urls import NoReverseMatch, reverse

logger = logging.getLogger(__name__)

WORKFLOW_ACTIONS: dict[str, list[dict[str, Any]]] = {
    "ADMIN": [
        {"key": "attendance", "label": "Take attendance today", "url_name": "portal:take_student_attendance", "clicks_saved": 2},
        {"key": "announcement", "label": "Send announcement", "url_name": "communication:announcement_create", "clicks_saved": 1},
        {"key": "fees", "label": "Review unpaid invoices", "url_name": "finance:invoices", "clicks_saved": 2},
        {"key": "reports", "label": "Open reports hub", "url_name": "reports:bulk_report_console", "clicks_saved": 1},
    ],
    "LEADERSHIP": [
        {"key": "attendance", "label": "Attendance overview", "url_name": "portal:take_student_attendance", "clicks_saved": 2},
        {"key": "staff_tasks", "label": "Staff tasks", "url_name": "accounts:backend_dashboard", "clicks_saved": 1},
    ],
    "PRINCIPAL": [
        {"key": "attendance", "label": "Take attendance today", "url_name": "portal:take_student_attendance", "clicks_saved": 2},
        {"key": "discipline", "label": "Behavior incidents", "url_name": "portal:discipline_incidents_list", "clicks_saved": 2},
    ],
    "TEACHER": [
        {"key": "gradebook", "label": "Open gradebook", "url_name": "portal:teacher_gradebook", "clicks_saved": 2},
        {"key": "attendance", "label": "Mark attendance", "url_name": "portal:take_student_attendance", "clicks_saved": 1},
        {"key": "assignments", "label": "Post assignment", "url_name": "portal:teacher_assignment_create", "clicks_saved": 2},
    ],
    "PARENT": [
        {"key": "messages", "label": "Message school", "url_name": "accounts:user_messages", "clicks_saved": 1},
        {"key": "fees", "label": "Pay fees", "url_name": "portal:parent_finance", "clicks_saved": 2},
        {"key": "student360", "label": "Student overview", "url_name": "portal:parent_dashboard", "clicks_saved": 1},
    ],
    "STUDENT": [
        {"key": "assignments", "label": "My assignments", "url_name": "portal:student_assignments", "clicks_saved": 1},
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
    """Resolve each action's destination, DROPPING any that has none.

    This used to emit ``url: ""`` when a name would not reverse, so a caller
    rendered a button that goes nowhere — a dead end produced by the very engine
    whose job is to save clicks. Twelve of the fifteen registry entries were in
    that state (every teacher, parent and student action), because the names had
    drifted as apps were reorganised and nothing ever checked them.

    Dropping is the safe direction: showing one fewer action costs a click,
    while showing a broken one costs trust. ``test_every_daily_ops_action_resolves``
    keeps the registry honest so this branch stays theoretical.
    """
    resolved: list[dict[str, Any]] = []
    for action in actions:
        row = dict(action)
        url_name = row.pop("url_name", "")
        if not url_name:
            continue
        try:
            row["url"] = reverse(url_name)
        except NoReverseMatch:
            logger.warning(
                "tenant_daily_ops: dropping action %r — %r does not reverse",
                row.get("key", ""),
                url_name,
            )
            continue
        resolved.append(row)
    return resolved
