"""Permission-filtered AI Center query orchestration."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from django.conf import settings

from services.ai.gateway import execute_engine_room_query
from services.ai.tenant_isolation import PlatformTier, SecurityIsolationException, TenantContextEnforcer
from services.ai_center.audit import emit_ai_center_event
from services.ai_center.constants import FEATURE_CODESPACE_DISCONNECT_PREFIX
from services.ai_center.indexing import get_feature_evidence, get_missing_context_reason, search_by_route
from services.ai_center.ollama_client import OllamaAICenterClient
from services.ai_center.redaction import redact_sensitive_text

Audience = Literal["operator", "tenant"]


@dataclass
class AICenterAnswer:
    answer: str
    audience: str
    route_context: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    missing_context: bool = False
    feature_absent: bool = False
    confidence: float = 0.0
    safety_flags: list[str] = field(default_factory=list)
    audit_id: str = ""
    provider: str = "rules"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _feature_in_ledger(feature_key: str) -> bool:
    if not feature_key:
        return True
    return bool(get_feature_evidence(feature_key))


def _operator_only_route(route_context: str, audience: Audience) -> bool:
    if audience != "tenant":
        return False
    low = (route_context or "").lower()
    return low.startswith("/super/") or "/super/" in low or low.startswith("/configuration/")


def answer_platform_question(
    *,
    user: Any,
    tenant: Any | None,
    role: str | None,
    route_context: str,
    question: str,
    audience: Audience = "tenant",
) -> AICenterAnswer:
    """
    Governed AI Center entry point. Extends services.ai.gateway when engine room is on.
    """
    audit_id = uuid.uuid4().hex
    safe_question = redact_sensitive_text(question or "")
    route_context = (route_context or "").strip()
    emit_ai_center_event(
        "ai_query_submitted",
        audit_id=audit_id,
        tenant_id=str(getattr(tenant, "pk", None) or getattr(tenant, "id", None) or ""),
        user_id=str(getattr(user, "pk", None) or ""),
        route_context=route_context,
        payload_summary={"audience": audience, "question_len": len(safe_question)},
    )

    if _operator_only_route(route_context, audience):
        emit_ai_center_event("ai_feature_absent", audit_id=audit_id, route_context=route_context)
        return AICenterAnswer(
            answer=FEATURE_CODESPACE_DISCONNECT_PREFIX,
            audience=audience,
            route_context=route_context,
            feature_absent=True,
            confidence=1.0,
            safety_flags=["operator_route_tenant_audience"],
            audit_id=audit_id,
            provider="rules",
        )

    try:
        enforcer = TenantContextEnforcer(user, school=tenant)
        scope = enforcer.resolve_scope()
        if tenant is not None and scope.tier == PlatformTier.PLATFORM_MANAGER:
            if not getattr(user, "is_superuser", False) and not getattr(user, "is_staff", False):
                raise SecurityIsolationException("cross_tenant_manager_scope")
    except SecurityIsolationException:
        emit_ai_center_event(
            "ai_gateway_error",
            audit_id=audit_id,
            payload_summary={"reason": "cross_tenant_block"},
        )
        return AICenterAnswer(
            answer="**Direct Answer**: This request cannot access another tenant's context.",
            audience=audience,
            route_context=route_context,
            safety_flags=["cross_tenant_block"],
            confidence=1.0,
            audit_id=audit_id,
            provider="rules",
        )

    if not bool(getattr(settings, "AI_GATEWAY_ENABLED", True)):
        emit_ai_center_event("ai_gateway_disabled_fallback", audit_id=audit_id)
        fallback = (
            "AI assistance is temporarily disabled. "
            "Use the Help Center or contact your school administrator."
        )
        return AICenterAnswer(
            answer=fallback,
            audience=audience,
            route_context=route_context,
            evidence=[],
            safety_flags=["ai_disabled"],
            confidence=0.4,
            audit_id=audit_id,
            provider="disabled",
        )

    for token in [t.strip("?,.") for t in safe_question.split() if t.strip("?,.")]:
        if "_" in token and len(token) >= 8 and not _feature_in_ledger(token):
            emit_ai_center_event("ai_feature_absent", audit_id=audit_id, route_context=route_context)
            return AICenterAnswer(
                answer=FEATURE_CODESPACE_DISCONNECT_PREFIX,
                audience=audience,
                route_context=route_context,
                feature_absent=True,
                confidence=0.9,
                audit_id=audit_id,
                provider="rules",
            )

    evidence = search_by_route(route_context) if route_context else get_feature_evidence(safe_question)
    missing = get_missing_context_reason(safe_question)
    if missing and not evidence:
        emit_ai_center_event("ai_missing_context", audit_id=audit_id, route_context=route_context)
        return AICenterAnswer(
            answer=missing,
            audience=audience,
            route_context=route_context,
            evidence=[],
            missing_context=True,
            confidence=0.5,
            audit_id=audit_id,
            provider="rules",
        )

    try:
        if bool(getattr(settings, "AI_ENGINE_ROOM_SUPPORT", True)):
            er = execute_engine_room_query(
                user,
                route_context or "/",
                safe_question,
                school=tenant,
                actor_is_staff=bool(getattr(user, "is_staff", False)),
                actor_is_superuser=bool(getattr(user, "is_superuser", False)),
            )
            text = (er.get("response") or "").strip() if isinstance(er, dict) else ""
            if text:
                emit_ai_center_event("ai_answer_generated", audit_id=audit_id)
                return AICenterAnswer(
                    answer=redact_sensitive_text(text),
                    audience=audience,
                    route_context=route_context,
                    evidence=[{"doc_id": e.get("doc_id"), "kind": e.get("kind")} for e in evidence[:8]],
                    confidence=0.85,
                    audit_id=audit_id,
                    provider="engine_room",
                )
    except Exception:
        pass

    client = OllamaAICenterClient()
    if client.enabled() and bool(getattr(settings, "AI_ALLOW_RULES_FALLBACK", True)):
        from services.ai.prompts import TENANT_FIRST_LINE_SUPPORT_SYSTEM

        system = TENANT_FIRST_LINE_SUPPORT_SYSTEM
        ctx_lines = "\n".join(f"- {e.get('text', '')[:200]}" for e in evidence[:6])
        user_prompt = f"Route: {route_context}\nEvidence:\n{ctx_lines}\n\nQuestion: {safe_question}"
        result = client.generate(system=system, user=user_prompt)
        if result.get("ok") and result.get("text"):
            emit_ai_center_event("ai_answer_generated", audit_id=audit_id)
            return AICenterAnswer(
                answer=redact_sensitive_text(result["text"]),
                audience=audience,
                route_context=route_context,
                evidence=[{"doc_id": e.get("doc_id")} for e in evidence[:8]],
                confidence=0.75,
                audit_id=audit_id,
                provider="ollama",
            )
        emit_ai_center_event(
            "ai_gateway_error",
            audit_id=audit_id,
            payload_summary={"error": result.get("error")},
        )

    outline = ""
    if route_context:
        try:
            from services.ai.code_oracle import build_route_manual_outline

            outline = build_route_manual_outline(route_context)
        except Exception:
            outline = ""
    answer = outline or (
        "**Direct Answer**: Indexed context is limited; open the Help Center for verified steps."
    )
    emit_ai_center_event("ai_gateway_disabled_fallback", audit_id=audit_id)
    return AICenterAnswer(
        answer=answer,
        audience=audience,
        route_context=route_context,
        evidence=[{"doc_id": e.get("doc_id")} for e in evidence[:5]],
        confidence=0.55,
        audit_id=audit_id,
        provider="rules",
    )
