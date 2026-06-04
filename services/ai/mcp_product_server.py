"""
Product MCP server scaffold (batch 1395).

Exposes a stable tool catalog for external MCP clients when
``RMC_PRODUCT_MCP_ENABLED=1``. Live LLM routing remains optional (Lane 2).

Tools are read-only or suggest-only — no silent writes.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "PRODUCT_MCP_TOOLS",
    "list_tools",
    "invoke_tool",
    "mcp_enabled",
]


PRODUCT_MCP_TOOLS: tuple[dict[str, Any], ...] = (
    {
        "name": "help_search",
        "description": "Search tenant KB titles (published only).",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
    {
        "name": "topology_search",
        "description": "Search navigation topology for menu paths.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
    {
        "name": "onboarding_status",
        "description": "Summarize activation checklist percent for bound school.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "interop_guidance",
        "description": "Return static interop hub pointers (no secrets).",
        "input_schema": {"type": "object", "properties": {"topic": {"type": "string"}}},
    },
    {
        "name": "lesson_plan_outline",
        "description": "Draft lesson outline (teacher review required; needs AI_TEACHER_COMMS).",
        "input_schema": {
            "type": "object",
            "properties": {
                "intent": {"type": "string"},
                "subject": {"type": "string"},
                "grade_level": {"type": "string"},
            },
            "required": ["intent"],
        },
    },
    {
        "name": "guide_surfaces",
        "description": "List RunMyCampus Guide surface keys for the authenticated role.",
        "input_schema": {"type": "object", "properties": {}},
    },
)


def mcp_enabled() -> bool:
    try:
        from django.conf import settings

        return bool(getattr(settings, "RMC_PRODUCT_MCP_ENABLED", False))
    except Exception:
        return False


def list_tools() -> list[dict[str, Any]]:
    return [dict(t) for t in PRODUCT_MCP_TOOLS]


def invoke_tool(
    name: str,
    arguments: dict[str, Any] | None,
    *,
    user: Any = None,
    school: Any = None,
) -> dict[str, Any]:
    args = arguments or {}
    if name == "help_search":
        q = str(args.get("query") or "").strip()[:200]
        if not q or school is None:
            return {"ok": False, "error": "query and school required"}
        try:
            from apps.portal.kb_context import published_kb_queryset

            qs = published_kb_queryset().filter(school=school)
            hits = list(
                qs.filter(title__icontains=q).values("slug", "title")[:8]
            )
            return {"ok": True, "articles": hits}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:200]}

    if name == "topology_search":
        q = str(args.get("query") or "").strip()[:200]
        if not q or user is None:
            return {"ok": False, "error": "query and user required"}
        try:
            from services.ai.topology_map import search_topology

            hits = search_topology(user, q, school=school, limit=5)
            return {"ok": True, "hits": hits}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:200]}

    if name == "onboarding_status":
        if school is None:
            return {"ok": False, "error": "school required"}
        try:
            from apps.platform_runtime.onboarding import get_school_onboarding_progress

            p = get_school_onboarding_progress(school, user=user)
            return {"ok": True, "percent": p.get("percent"), "completed": p.get("completed"), "total": p.get("total")}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:200]}

    if name == "interop_guidance":
        topic = str(args.get("topic") or "general")[:80]
        return {
            "ok": True,
            "summary": f"Interop topic: {topic}. Use district/LMS interop hub and OneRoster readiness APIs.",
            "routes": [
                "/authentication/backend/district-lms-interop/",
                "/api/interop/oneroster/",
                "/api/interop/lti13/",
            ],
        }

    if name == "lesson_plan_outline":
        intent = str(args.get("intent") or "").strip()[:500]
        if not intent or school is None:
            return {"ok": False, "error": "intent and school required"}
        try:
            from apps.billing.entitlements import can

            if not can(school, "AI_TEACHER_COMMS"):
                return {"ok": False, "error": "AI_TEACHER_COMMS not enabled"}
        except Exception:
            return {"ok": False, "error": "entitlement check failed"}
        try:
            from services.teacher_lesson_plan import draft_lesson_plan_outline

            teacher = getattr(user, "teacher_profile", None) if user is not None else None
            text, meta = draft_lesson_plan_outline(
                school=school,
                teacher=teacher,
                subject=str(args.get("subject") or "")[:120],
                grade_level=str(args.get("grade_level") or "")[:80],
                intent=intent,
            )
            if not text:
                return {"ok": False, "error": meta.get("error") or "no draft"}
            return {"ok": True, "outline": text[:2500], "provider": meta.get("provider", "")}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:200]}

    if name == "guide_surfaces":
        if user is None:
            return {"ok": False, "error": "user required"}
        try:
            from apps.portal.views_runmycampus_guide import _guide_surfaces

            class _Req:
                pass

            req = _Req()
            req.user = user
            req.school = school
            req.path = "/portal/guide/"
            surfaces = _guide_surfaces(req)
            return {
                "ok": True,
                "surfaces": [
                    {"key": s["key"], "title": s["title"], "intent": s.get("intent")}
                    for s in surfaces
                ],
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:200]}

    return {"ok": False, "error": f"unknown tool: {name}"}
