"""
Support assistant SSE stream — Ollama token stream with engine-room guardrails.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Iterator

from django.conf import settings

from services.ai.gateway import (
    _finalize_model_text,
    _max_input_tokens,
    _route_permission_denied,
    _query_permission_denied,
    _engine_room_enabled,
)
from services.ai.knowledge import permission_labels_for_user, retrieve_knowledge_snippets
from services.ai.platform_context import build_tier_context_block
from services.ai.prompts import (
    PLATFORM_SRE_SYSTEM,
    TENANT_FIRST_LINE_SUPPORT_SYSTEM,
    assemble_ollama_payload,
)
from services.ai.reflection import DynamicSystemInspector, match_path_with_test_hooks
from services.ai.support_sse import format_sse_frame, heartbeat_frame
from services.ai.support_intent import (
    SupportIntent,
    classify_support_intent,
    intent_prompt_hint,
)
from services.ai.support_sanitize import sanitize_support_query
from services.ai.tenant_isolation import PlatformTier, TenantContextEnforcer
from services.ai.token_optimizer import ContextTokenCompressor
from services.inference import OllamaInferenceService

logger = logging.getLogger(__name__)

_SSE_HEARTBEAT_SECONDS = 25.0
_SSE_MAX_SECONDS = 90.0


def _early_done(
    *,
    response: str,
    escalation_required: bool,
    meta: dict[str, Any],
) -> Iterator[bytes]:
    yield format_sse_frame(
        event="done",
        payload={
            "success": True,
            "response": response,
            "escalation_required": escalation_required,
            "meta": meta,
        },
        event_id="done",
    )


def iter_support_assistant_sse(
    user_profile: Any,
    active_url: str,
    user_query: str,
    *,
    school: Any | None = None,
    actor_roles: list[str] | None = None,
    actor_is_staff: bool = False,
    actor_is_superuser: bool = False,
    interaction_history: str = "",
    request=None,
) -> Iterator[bytes]:
    started = time.perf_counter()
    query = sanitize_support_query((user_query or "").strip()[:8000])
    history = sanitize_support_query((interaction_history or "").strip()[:2000])
    active = (active_url or "/").strip() or "/"
    language = "en"
    if request is not None:
        try:
            from django.utils import translation

            language = (translation.get_language() or "en")[:12]
        except Exception:
            language = "en"

    if not query:
        yield format_sse_frame(
            event="error",
            payload={"success": False, "error": "query required"},
            event_id="error",
        )
        return

    if not _engine_room_enabled():
        yield format_sse_frame(
            event="error",
            payload={"success": False, "error": "AI engine room disabled"},
            event_id="error",
        )
        return

    yield format_sse_frame(
        event="meta",
        payload={"engine_room": True, "transport": "sse", "language": language},
        event_id="meta",
    )

    from services.ai_copilot_rbac import prepare_engine_room_rbac

    rbac = prepare_engine_room_rbac(
        user_profile,
        query,
        school=school,
        active_url=active,
        task_type="support_suggest",
    )
    if not rbac.allowed:
        yield from _early_done(
            response=rbac.denial_reason,
            escalation_required=False,
            meta={
                "outcome": "permission_refusal",
                "skipped_model": True,
                "copilot_rbac_enforced": True,
                "rbac_scope": rbac.permissions.get("scope"),
                "language": language,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return

    enforcer = TenantContextEnforcer(user_profile, school=school)
    scope = enforcer.resolve_scope()
    perm_labels = permission_labels_for_user(user_profile, school=school)
    inspector = DynamicSystemInspector()
    route = match_path_with_test_hooks(inspector, active) or inspector.match_path(active)
    route_perms = list((route or {}).get("required_permissions") or [])
    intent = classify_support_intent(query, active_url=active, route_row=route)

    if (
        intent == SupportIntent.UI_NAVIGATION_HELP
        and school is not None
        and not actor_is_superuser
    ):
        try:
            from apps.portal.kb_embeddings import (
                DEFLECTION_SCORE_THRESHOLD,
                search_kb_articles_by_embedding,
            )
            from services.ai_memory import get_embedding_for_text

            embedding = get_embedding_for_text(query, max_tokens=512)
            if embedding:
                operator = scope.tier == PlatformTier.PLATFORM_MANAGER
                hits = search_kb_articles_by_embedding(
                    school=school,
                    query_embedding=embedding,
                    limit=1,
                    operator=operator,
                )
                if hits and hits[0][1] >= DEFLECTION_SCORE_THRESHOLD:
                    article, score = hits[0]
                    from django.urls import reverse

                    try:
                        article_url = reverse(
                            "kb:kb_article", kwargs={"article_slug": article.slug}
                        )
                    except Exception:
                        article_url = active
                    yield from _early_done(
                        response=(
                            f"**Direct Answer**: {article.title}\n"
                            f"**Execution Path**: Open the knowledge base article linked below.\n"
                            f"**Action Steps**:\n1. Review \"{article.title}\".\n"
                            f"2. If that resolves your question, no ticket is needed."
                        ),
                        escalation_required=False,
                        meta={
                            "outcome": "deflection_card",
                            "intent": intent.value,
                            "deflection_score": round(score, 4),
                            "article_slug": article.slug,
                            "article_url": article_url,
                            "skipped_model": True,
                            "language": language,
                        },
                    )
                    return
        except Exception as exc:
            logger.debug("support deflection card skipped: %s", exc)

    context_header = enforcer.build_context_header(
        active_url=active,
        permission_labels=perm_labels + route_perms,
    )
    tier_block = build_tier_context_block(scope, school)
    user_context_block = f"{rbac.prompt}\n\n{context_header}\n{tier_block}"

    denial = _query_permission_denied(user_profile, query) or _route_permission_denied(
        user_profile,
        route_perms=route_perms,
        scope=scope.tier,
    )
    if denial:
        yield from _early_done(
            response=denial,
            escalation_required=False,
            meta={
                "outcome": "permission_refusal",
                "tier": scope.tier.value,
                "skipped_model": True,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return

    knowledge_lines, rag_snippets = retrieve_knowledge_snippets(
        user=user_profile,
        school=school,
        user_query=query,
        scope=scope.tier,
        actor_roles=actor_roles,
        actor_is_staff=actor_is_staff,
        actor_is_superuser=actor_is_superuser,
    )
    if intent == SupportIntent.TROUBLESHOOTING_ERROR and (
        actor_is_staff or actor_is_superuser or scope.tier == PlatformTier.PLATFORM_MANAGER
    ):
        from services.ai.code_index import search_code_index

        vis = "operator" if scope.tier == PlatformTier.PLATFORM_MANAGER else "staff"
        knowledge_lines = search_code_index(query, limit=3, visibility=vis) + knowledge_lines
    elif intent == SupportIntent.API_DEVELOPER_SUPPORT:
        knowledge_lines = [
            "- API: Use API Center schema UI and Redoc at /api/schema/ui/ for endpoint contracts."
        ] + knowledge_lines
    if not knowledge_lines:
        from services.ai.code_oracle import build_route_manual_outline

        outline = build_route_manual_outline(active)
        if outline:
            knowledge_lines = [outline]
        else:
            from services.ai.gateway import _escalation_for_scope

            yield from _early_done(
                response=_escalation_for_scope(scope.tier),
                escalation_required=True,
                meta={
                    "outcome": "escalation_no_docs",
                    "tier": scope.tier.value,
                    "skipped_model": True,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            return

    system_prompt = (
        PLATFORM_SRE_SYSTEM
        if scope.tier == PlatformTier.PLATFORM_MANAGER
        else TENANT_FIRST_LINE_SUPPORT_SYSTEM
    )
    hint = intent_prompt_hint(intent, language=language)
    if hint:
        system_prompt = f"{system_prompt}\n\n[INTENT]\n{hint}\n"
    if language and not language.startswith("en"):
        system_prompt = (
            f"{system_prompt}\nRespond entirely in the user's active language ({language}).\n"
        )
    knowledge_text = "\n".join(knowledge_lines)
    screen_block = f"Active route signals: {', '.join(route_perms) or 'none'}"
    compressor = ContextTokenCompressor(max_input_tokens=_max_input_tokens())
    compressed = compressor.compress(
        permission_block=user_context_block,
        screen_block=screen_block,
        knowledge_block=knowledge_text,
        history_block=history,
    )
    prompt = assemble_ollama_payload(
        system_prompt=system_prompt,
        user_context_block=compressed.as_prompt_sections(),
        knowledge_snippets=compressed.knowledge_block,
        user_question=query,
    )

    use_ollama_stream = bool(getattr(settings, "SUPPORT_AI_OLLAMA_STREAM", True))
    last_ping = time.perf_counter()
    parts: list[str] = []

    if use_ollama_stream:
        try:
            for chunk in OllamaInferenceService.stream_generate(
                system_prompt=system_prompt,
                user_prompt=prompt,
                request=request,
                school=school,
            ):
                parts.append(chunk)
                yield format_sse_frame(
                    event="delta",
                    payload={"text": chunk},
                    event_id=str(len(parts)),
                )
                now = time.perf_counter()
                if now - last_ping >= _SSE_HEARTBEAT_SECONDS:
                    yield heartbeat_frame()
                    last_ping = now
                if now - started >= _SSE_MAX_SECONDS:
                    break
        except Exception as exc:
            logger.warning("support assistant ollama stream failed: %s", exc)
            parts = []

    if not parts:
        from services.ai.gateway import process_platform_query

        engine = process_platform_query(
            user_profile,
            active,
            query,
            school=school,
            actor_roles=actor_roles,
            actor_is_staff=actor_is_staff,
            actor_is_superuser=actor_is_superuser,
            interaction_history=interaction_history,
        )
        text = engine.get("response") or ""
        chunk_size = max(12, len(text) // 32) if text else 0
        for i in range(0, len(text), chunk_size):
            piece = text[i : i + chunk_size]
            parts.append(piece)
            yield format_sse_frame(
                event="delta",
                payload={"text": piece},
                event_id=str(len(parts)),
            )
        yield from _early_done(
            response=text,
            escalation_required=bool(engine.get("escalation_required")),
            meta=engine.get("meta") or {},
        )
        return

    raw = "".join(parts)
    text, escalation = _finalize_model_text(raw, scope=scope.tier)
    meta = {
        "engine_room": True,
        "rag_snippets": rag_snippets,
        "truncated_context": compressed.truncated,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "tier_scope": scope.tier.value,
        "stream": "ollama",
        "copilot_rbac_enforced": True,
        "rbac_scope": rbac.permissions.get("scope"),
    }
    if escalation:
        meta["outcome"] = "escalation_model_output"
    yield from _early_done(
        response=text,
        escalation_required=escalation,
        meta=meta,
    )
