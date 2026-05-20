"""Contextual in-app micro-insights (data-ai-contextual-insight)."""

from __future__ import annotations

from typing import Any

from services.ai_center.audit import emit_ai_center_event
from services.ai_center.indexing import search_by_route
from services.ai_center.query_service import answer_platform_question


def get_contextual_tip(
    user: Any,
    tenant: Any | None,
    route: str,
    module: str,
    current_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Short tip for inline UI markers. Never auto-runs destructive actions.
    """
    state = current_state or {}
    audience = "operator" if getattr(user, "is_staff", False) else "tenant"
    question = f"What should I do next on {module}?"
    if state.get("error_code"):
        question = f"How do I resolve {state['error_code']} on {module}?"

    hits = search_by_route(route, limit=2)
    if hits:
        tip = hits[0].get("text", "")[:220]
    else:
        result = answer_platform_question(
            user=user,
            tenant=tenant,
            role=getattr(user, "role", None),
            route_context=route,
            question=question,
            audience=audience,
        )
        tip = (result.answer or "")[:220]

    emit_ai_center_event(
        "ai_contextual_tip_generated",
        route_context=route,
        payload_summary={"module": module, "tip_len": len(tip)},
    )
    return {
        "tip": tip,
        "route": route,
        "module": module,
        "ui_marker": "data-ai-contextual-insight",
        "audience": audience,
    }
