"""
Engine-room orchestration: topology + RAG + constrained Ollama prompt assembly.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from django.conf import settings

from services.ai.knowledge import permission_labels_for_user, retrieve_knowledge_snippets
from services.ai.platform_context import build_tier_context_block
from services.ai.prompts import (
    ESCALATION_USER_MESSAGE,
    PLATFORM_ESCALATION_MESSAGE,
    PLATFORM_SRE_SYSTEM,
    TENANT_FIRST_LINE_SUPPORT_SYSTEM,
    assemble_ollama_payload,
    looks_like_hallucinated_fluff,
    validate_response_structure,
)
from services.ai.reflection import DynamicSystemInspector, match_path_with_test_hooks
from services.ai.tenant_isolation import PlatformTier, TenantContextEnforcer
from services.ai.token_optimizer import ContextTokenCompressor

logger = logging.getLogger(__name__)

_MAX_USER_QUERY_CHARS = 8000


def _engine_room_enabled() -> bool:
    if not bool(getattr(settings, "AI_GATEWAY_ENABLED", True)):
        return False
    return bool(getattr(settings, "AI_ENGINE_ROOM_SUPPORT", True))


def _timeout_seconds() -> int:
    raw = getattr(settings, "AI_ENGINE_ROOM_TIMEOUT_SECONDS", None) or 15
    try:
        return max(3, min(int(raw), 90))
    except (TypeError, ValueError):
        return 15


def _max_input_tokens() -> int:
    raw = getattr(settings, "AI_ENGINE_ROOM_MAX_INPUT_TOKENS", None) or 6000
    try:
        return max(1024, int(raw))
    except (TypeError, ValueError):
        return 6000


_FINANCE_QUERY_MARKERS = (
    "financial ledger",
    "clear ledger",
    "delete ledger",
    "tuition rate",
    "modify tuition",
    "wipe ledger",
    "clear out financial",
)


def _query_permission_denied(user: Any, user_query: str) -> str | None:
    q = (user_query or "").lower()
    if not any(m in q for m in _FINANCE_QUERY_MARKERS):
        return None
    role = str(getattr(user, "role", "") or "").upper()
    if role in {"BURSAR", "FINANCE_STAFF", "ACCOUNTANT", "ADMIN", "PROPRIETOR", "LEADERSHIP"}:
        return None
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return None
    role_label = getattr(user, "role", None) or "your role"
    return (
        f"**Direct Answer**: As a {role_label}, you cannot modify or clear financial ledgers.\n"
        f"**Execution Path**: **Contact your Campus Business Manager or Bursar**\n"
        f"**Action Steps**:\n"
        f"1. Open an internal request to Finance describing the needed change.\n"
        f"2. Wait for a user with BURSAR or FINANCE_STAFF clearance to execute it.\n"
        f"**System Bound**: You do not possess ledger clearance; do not attempt bulk deletes."
    )


def _route_permission_denied(
    user: Any,
    *,
    route_perms: list[str],
    scope: PlatformTier,
) -> str | None:
    if not route_perms:
        return None
    needs_staff = any(p in route_perms for p in ("staff_required", "drf:IsAdminUser"))
    if needs_staff and scope == PlatformTier.SCHOOL_TENANT:
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            role = getattr(user, "role", None) or "your role"
            return (
                f"**Direct Answer**: As {role}, you do not have staff clearance for this screen.\n"
                f"**Execution Path**: Request elevated access from your school administrator.\n"
                f"**Action Steps**:\n"
                f"1. Contact your school IT admin or principal.\n"
                f"2. Ask them to grant staff-level access or perform the action for you.\n"
                f"**System Bound**: Required route signals: {', '.join(route_perms)}."
            )
    finance_markers = ("finance", "billing", "ledger", "tuition", "bursar")
    q_low = " ".join(route_perms).lower()
    if any(m in q_low for m in finance_markers):
        role = str(getattr(user, "role", "") or "").upper()
        if role not in {"BURSAR", "FINANCE_STAFF", "ACCOUNTANT", "ADMIN", "PROPRIETOR", "LEADERSHIP"}:
            if not getattr(user, "is_staff", False):
                return (
                    "**Direct Answer**: You do not have financial clearance for this workflow.\n"
                    "**Execution Path**: **Finance > Contact Bursar**\n"
                    "**Action Steps**:\n"
                    "1. Route the request to your Campus Business Manager.\n"
                    "**System Bound**: Financial routes require finance or staff clearance."
                )
    return None


def _escalation_for_scope(scope: PlatformTier) -> str:
    if scope == PlatformTier.PLATFORM_MANAGER:
        return PLATFORM_ESCALATION_MESSAGE
    return ESCALATION_USER_MESSAGE


def _finalize_model_text(
    text: str,
    *,
    scope: PlatformTier,
) -> tuple[str, bool]:
    """Validate structure; escalate on fluff or missing sections."""
    blob = (text or "").strip()
    if not blob or looks_like_hallucinated_fluff(blob):
        return _escalation_for_scope(scope), True
    ok, missing = validate_response_structure(blob)
    if not ok and missing:
        logger.debug("engine room response missing sections: %s", missing)
        return _escalation_for_scope(scope), True
    return blob, False


def execute_engine_room_query(
    user_profile: Any,
    active_url: str,
    user_query: str,
    *,
    school: Any | None = None,
    actor_roles: list[str] | None = None,
    actor_is_staff: bool = False,
    actor_is_superuser: bool = False,
    interaction_history: str = "",
) -> dict[str, Any]:
    return process_platform_query(
        user_profile,
        active_url,
        user_query,
        school=school,
        actor_roles=actor_roles,
        actor_is_staff=actor_is_staff,
        actor_is_superuser=actor_is_superuser,
        interaction_history=interaction_history,
    )


def process_platform_query(
    user_profile: Any,
    active_url: str,
    user_query: str,
    *,
    school: Any | None = None,
    actor_roles: list[str] | None = None,
    actor_is_staff: bool = False,
    actor_is_superuser: bool = False,
    interaction_history: str = "",
) -> dict[str, Any]:
    started = time.perf_counter()
    from services.ai.support_sanitize import sanitize_support_query

    query = sanitize_support_query((user_query or "").strip())
    if len(query) > _MAX_USER_QUERY_CHARS:
        query = query[:_MAX_USER_QUERY_CHARS]
    active = (active_url or "/").strip() or "/"

    out: dict[str, Any] = {
        "success": False,
        "response": "",
        "escalation_required": False,
        "meta": {"engine_room": True},
    }

    if not query:
        out["error"] = "query required"
        return out

    if not _engine_room_enabled():
        out["error"] = "AI engine room disabled"
        out["meta"]["gateway_enabled"] = False
        return out

    enforcer = TenantContextEnforcer(user_profile, school=school)
    scope = enforcer.resolve_scope()
    perm_labels = permission_labels_for_user(user_profile, school=school)

    inspector = DynamicSystemInspector()
    route = match_path_with_test_hooks(inspector, active) or inspector.match_path(active)
    route_perms = list((route or {}).get("required_permissions") or [])

    context_header = enforcer.build_context_header(
        active_url=active,
        permission_labels=perm_labels + route_perms,
    )
    tier_block = build_tier_context_block(scope, school)
    user_context_block = f"{context_header}\n{tier_block}"

    denial = _query_permission_denied(user_profile, query) or _route_permission_denied(
        user_profile,
        route_perms=route_perms,
        scope=scope.tier,
    )
    if denial:
        out["success"] = True
        out["response"] = denial
        out["meta"].update(
            {
                "outcome": "permission_refusal",
                "tier": scope.tier.value,
                "skipped_model": True,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        )
        return out

    try:
        from apps.portal.school_help_context import build_school_help_context_block

        school_block = build_school_help_context_block(
            school=school, user=user_profile
        )
    except Exception:
        school_block = ""

    knowledge_lines, rag_snippets = retrieve_knowledge_snippets(
        user=user_profile,
        school=school,
        user_query=query,
        scope=scope.tier,
        actor_roles=actor_roles,
        actor_is_staff=actor_is_staff,
        actor_is_superuser=actor_is_superuser,
    )
    if school_block:
        knowledge_lines = [school_block] + list(knowledge_lines)

    if not knowledge_lines:
        from services.ai.code_oracle import build_route_manual_outline

        outline = build_route_manual_outline(active)
        if outline:
            knowledge_lines = [outline]
            rag_snippets = [{"scope": "topology", "metadata": {"source": "code_oracle"}}]
        else:
            out["success"] = True
            out["response"] = _escalation_for_scope(scope.tier)
            out["escalation_required"] = True
            out["meta"].update(
                {
                    "outcome": "escalation_no_docs",
                    "tier": scope.tier.value,
                    "skipped_model": True,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                }
            )
            return out

    system_prompt = (
        PLATFORM_SRE_SYSTEM
        if scope.tier == PlatformTier.PLATFORM_MANAGER
        else TENANT_FIRST_LINE_SUPPORT_SYSTEM
    )

    knowledge_text = "\n".join(knowledge_lines)
    screen_block = f"Active route signals: {', '.join(route_perms) or 'none'}"

    compressor = ContextTokenCompressor(max_input_tokens=_max_input_tokens())
    compressed = compressor.compress(
        permission_block=user_context_block,
        screen_block=screen_block,
        knowledge_block=knowledge_text,
        history_block=(interaction_history or "")[:2000],
    )
    prompt = assemble_ollama_payload(
        system_prompt=system_prompt,
        user_context_block=compressed.as_prompt_sections(),
        knowledge_snippets=compressed.knowledge_block,
        user_question=query,
    )

    school_id = scope.tenant_id
    try:
        from services.ai_gateway import TaskType, invoke

        result, meta = invoke(
            TaskType.SUPPORT_SUGGEST,
            prompt,
            user_query=query,
            metadata={
                "tenant_id": school_id,
                "school_id": school_id,
                "school": school,
                "user_id": scope.user_id,
                "role": scope.role,
                "rag_snippets": rag_snippets,
                "latency_target": _timeout_seconds(),
                "northstar_prompt_type": "first_line_support",
                "active_url": active,
            },
        )
        raw = result if isinstance(result, str) else str(result or "")
        text, escalation = _finalize_model_text(raw, scope=scope.tier)
        out["success"] = True
        out["response"] = text
        out["escalation_required"] = escalation
        out["meta"].update(meta or {})
        out["meta"]["truncated_context"] = compressed.truncated
        out["meta"]["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        out["meta"]["tier_scope"] = scope.tier.value
        if escalation:
            out["meta"]["outcome"] = "escalation_model_output"
        return out
    except Exception as exc:
        logger.warning("engine room invoke failed: %s", exc)
        out["success"] = True
        out["response"] = _escalation_for_scope(scope.tier)
        out["escalation_required"] = True
        out["meta"]["outcome"] = "invoke_error"
        out["meta"]["error"] = str(exc)
        out["meta"]["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        return out
