"""
Universal command bar search — topology + engine-room documentation snippets.
"""

from __future__ import annotations

import logging
from typing import Any

from services.ai.gateway import process_platform_query
from services.ai.prompts import COMMAND_BAR_SNIPPET_HINT
from services.ai.knowledge import permission_labels_for_user
from services.ai.topology_map import search_topology
from services.ai.tenant_isolation import TenantContextEnforcer

logger = logging.getLogger(__name__)


def search_command_bar(
    user: Any,
    query: str,
    *,
    active_url: str = "",
    school: Any | None = None,
    actor_roles: list[str] | None = None,
    actor_is_staff: bool = False,
    actor_is_superuser: bool = False,
    include_ai_snippet: bool = True,
) -> dict[str, Any]:
    """
    Returns { results: [...], permissions: [...], ai_snippet: str|None, escalation_required: bool }.
    """
    q = (query or "").strip()
    enforcer = TenantContextEnforcer(user, school=school)
    scope = enforcer.resolve_scope()

    nav = search_topology(user, q, school=school, limit=10)
    results: list[dict[str, Any]] = []

    for row in nav:
        item = {
            "type": "locked" if row.get("locked") else row.get("kind", "navigate"),
            "label": row.get("label"),
            "path_label": row.get("path_label"),
            "url": row.get("url"),
            "missing_permission": row.get("missing_permission"),
            "icon": "bi-lock-fill" if row.get("locked") else "bi-arrow-right-circle",
        }
        if row.get("locked"):
            item["detail"] = (
                f"Requires {row.get('missing_permission')} clearance. "
                "Contact your school administrator or platform operator."
            )
        results.append(item)

    ai_snippet = None
    escalation = False
    if include_ai_snippet and len(q) >= 4:
        try:
            engine = process_platform_query(
                user,
                active_url,
                f"{COMMAND_BAR_SNIPPET_HINT}\n\n{q}",
                school=school,
                actor_roles=actor_roles,
                actor_is_staff=actor_is_staff,
                actor_is_superuser=actor_is_superuser,
            )
            if engine.get("success") and engine.get("response"):
                if not engine.get("escalation_required"):
                    ai_snippet = str(engine.get("response"))[:600]
                    results.insert(
                        0,
                        {
                            "type": "documentation",
                            "label": f"How-to: {q[:60]}",
                            "path_label": "**AI Engine Room**",
                            "detail": ai_snippet,
                            "url": None,
                            "icon": "bi-journal-text",
                            "ask_ai_center": True,
                        },
                    )
                else:
                    escalation = True
                    results.insert(
                        0,
                        {
                            "type": "escalate",
                            "label": "Escalate to Campus Helpdesk",
                            "path_label": "**Support > Helpdesk**",
                            "detail": engine.get("response"),
                            "url": None,
                            "icon": "bi-life-preserver",
                        },
                    )
        except Exception as exc:
            logger.debug("command bar AI snippet skipped: %s", exc)

    return {
        "results": results,
        "permissions": permission_labels_for_user(user, school=school),
        "tier": scope.tier.value,
        "ai_snippet": ai_snippet,
        "escalation_required": escalation,
    }
