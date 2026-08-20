"""
Expand tenant daily ops — per-workflow next-best actions with resolved URLs.
"""

from __future__ import annotations

import logging
from typing import Any

from django.urls import NoReverseMatch, reverse

from apps.platform_runtime.click_budget import (
    clicks_saved_for_path,
    clicks_saved_for_url_name,
)

logger = logging.getLogger(__name__)

WORKFLOW_ACTIONS: dict[str, list[dict[str, Any]]] = {
    "ADMIN": [
        {"key": "attendance", "label": "Take attendance today", "url_name": "portal:take_student_attendance"},
        {"key": "announcement", "label": "Send announcement", "url_name": "communication:announcement_create"},
        {"key": "fees", "label": "Review unpaid invoices", "url_name": "finance:invoices"},
        {"key": "reports", "label": "Open reports hub", "url_name": "reports:bulk_report_console"},
    ],
    "LEADERSHIP": [
        {"key": "attendance", "label": "Attendance overview", "url_name": "portal:take_student_attendance"},
        {"key": "staff_tasks", "label": "Staff tasks", "url_name": "accounts:backend_dashboard"},
    ],
    "PRINCIPAL": [
        {"key": "attendance", "label": "Take attendance today", "url_name": "portal:take_student_attendance"},
        {"key": "discipline", "label": "Behavior incidents", "url_name": "portal:discipline_incidents_list"},
    ],
    "TEACHER": [
        {"key": "gradebook", "label": "Open gradebook", "url_name": "portal:teacher_gradebook"},
        {"key": "attendance", "label": "Mark attendance", "url_name": "portal:take_student_attendance"},
        {"key": "assignments", "label": "Post assignment", "url_name": "portal:teacher_assignment_create"},
    ],
    "PARENT": [
        {"key": "messages", "label": "Message school", "url_name": "accounts:user_messages"},
        {"key": "fees", "label": "Pay fees", "url_name": "portal:parent_finance"},
        {"key": "student360", "label": "Student overview", "url_name": "portal:parent_dashboard"},
    ],
    "STUDENT": [
        {"key": "assignments", "label": "My assignments", "url_name": "portal:student_assignments"},
    ],
}


def next_best_actions_for_role(school, user) -> list[dict[str, Any]]:
    """Per-role next-best actions, stamped with the calling tenant.

    Each row is COPIED before it is stamped. ``list(...)`` clones the list but
    not the dicts inside it, so the previous version wrote ``school_id`` into
    the module-level ``WORKFLOW_ACTIONS`` entries themselves — one shared
    mutable table, one school's id, every request. It was overwritten on the
    next call, which is what kept it from being obvious, and is also exactly
    what makes it dangerous under a threaded server: two requests interleaving
    between the stamp and the read hands one school the other's id.
    """
    role = (getattr(user, "role", "") or "").upper()
    actions = [
        dict(action)
        for action in WORKFLOW_ACTIONS.get(role, WORKFLOW_ACTIONS.get("ADMIN", []))
    ]
    sid = str(getattr(school, "pk", "") or "")
    for action in actions:
        action["school_id"] = sid
        action["workflow"] = action.get("key", "")
        # Derived from the destination, so callers reading the un-resolved rows
        # still get the metric. resolve_action_urls recomputes it from the path
        # that actually reversed, which is the authoritative one.
        action["clicks_saved"] = clicks_saved_for_url_name(action.get("url_name", ""))
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
            url = reverse(url_name)
        except NoReverseMatch:
            logger.warning(
                "tenant_daily_ops: dropping action %r — %r does not reverse",
                row.get("key", ""),
                url_name,
            )
            continue
        row["url"] = url
        # Derived, never asserted. See apps.platform_runtime.click_budget for
        # why a hand-written number here was worth less than no number at all.
        row["clicks_saved"] = clicks_saved_for_path(url)
        resolved.append(row)
    return resolved
