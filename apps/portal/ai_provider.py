"""
AI provider abstraction for sovereign/local-first execution.

Priority order is configurable and defaults to:
    ollama -> rules (local-first).

All generative chat for the product goes through ``services.ai_gateway.invoke`` when
``AI_GATEWAY_ENABLED`` is true; this module supplies Ollama delegation and status for
operators. External cloud LLMs (removed: former Gemini path) are not used — inference
defaults to self-hosted Ollama via the gateway, then rules. vLLM/LiteLLM are optional
only when enabled per-task in Django ``AI_GATEWAY_TASK_TIERS``.

Set ``AI_PROVIDER_PREFERENCE`` to e.g. ``ollama,rules`` (default). Legacy values
mentioning ``gemini`` are ignored.

`metadata` is intentionally not appended to model prompts so tenant identifiers
or internal IDs are not sent to inference backends.

Sync vs async: Use generate_ai_response (sync) for single-turn copilot only. For bulk
or long-running (syllabus sync, bulk support suggestion, report-card remarks), use
apps.portal.tasks.generate_ai_response_async and poll cache key ai:async_result:{task_id}.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

# Typed exceptions for AI gateway invoke (support §2.4 broad-except replacement).
_AI_GATEWAY_INVOKE_ERRORS = (
    OSError,
    ConnectionError,
    TimeoutError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ImportError,
)

# Local-first default: Ollama then rules only.
DEFAULT_PROVIDER_ORDER = ["ollama", "rules"]
_DISALLOWED_PREFERENCE_TOKENS = frozenset({"gemini"})
PROMPT_INJECTION_PATTERNS = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "reveal system prompt",
    "show system prompt",
    "developer instructions",
    "print secrets",
    "show secrets",
    "drop table",
)


def _provider_preference() -> list[str]:
    raw = (
        getattr(settings, "AI_PROVIDER_PREFERENCE", None)
        or os.environ.get("AI_PROVIDER_PREFERENCE")
        or ",".join(DEFAULT_PROVIDER_ORDER)
    )
    items = [p.strip().lower() for p in str(raw).split(",") if p.strip()]
    items = [p for p in items if p not in _DISALLOWED_PREFERENCE_TOKENS]
    deduped: list[str] = []
    for item in items:
        if item not in deduped:
            deduped.append(item)
    if "rules" not in deduped:
        deduped.append("rules")
    return deduped


def _request_timeout_seconds() -> int:
    raw = (
        getattr(settings, "AI_PROVIDER_TIMEOUT_SECONDS", None)
        or os.environ.get("AI_PROVIDER_TIMEOUT_SECONDS")
        or "20"
    )
    try:
        return max(5, min(int(raw), 60))
    except (TypeError, ValueError):
        return 20


def _ollama_config() -> tuple[str, str]:
    endpoint = (
        getattr(settings, "OLLAMA_ENDPOINT", None)
        or os.environ.get("OLLAMA_ENDPOINT")
        or "http://localhost:11434/api/generate"
    ).strip()
    model = (
        getattr(settings, "OLLAMA_MODEL", None)
        or os.environ.get("OLLAMA_MODEL")
        or "llama3"
    ).strip()
    return endpoint, model


def _call_ollama(prompt: str, metadata: dict[str, Any] | None = None) -> str | None:
    """
    Single Ollama entry point: delegates to OllamaInferenceService (region, dossier, cache, fallback).
    Resolves school/tenant/country from metadata; no direct HTTP here (F.1).
    """
    from services.inference import OllamaInferenceService

    md = metadata or {}
    text, _meta = OllamaInferenceService.infer(
        system_prompt="",
        user_prompt=prompt,
        request=md.get("request"),
        school=md.get("school"),
        country_code=md.get("country_code"),
    )
    return text


def _rules_fallback(user_query: str) -> str:
    query = (user_query or "").strip()
    if not query:
        return "I can help with school operations, finance, academics, and compliance."
    return (
        "I can help with that request, but live AI providers are currently unavailable. "
        f"Request received: {query[:180]}"
    )


def _is_policy_denied(user_query: str) -> bool:
    text = (user_query or "").strip().lower()
    if not text:
        return False
    return any(pattern in text for pattern in PROMPT_INJECTION_PATTERNS)


def _normalize_gateway_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    md = dict(metadata or {})
    request = md.get("request")
    school = md.get("school") or getattr(request, "school", None)
    if school is not None:
        md.setdefault("school", school)
    if md.get("school_id") is None and school is not None:
        school_id = getattr(school, "pk", None) or getattr(school, "id", None)
        if school_id is not None:
            md["school_id"] = school_id
    if md.get("tenant_id") is None and md.get("school_id") is not None:
        md["tenant_id"] = md["school_id"]
    if md.get("country_code") in (None, "") and school is not None:
        country_code = getattr(school, "country_code", None) or getattr(
            getattr(school, "default_region", None),
            "code",
            None,
        )
        if country_code:
            md["country_code"] = country_code
    if md.get("user_id") is None and request is not None:
        user = getattr(request, "user", None)
        user_id = getattr(user, "pk", None) or getattr(user, "id", None)
        if user_id is not None:
            md["user_id"] = user_id
    if md.get("role") is None and request is not None:
        user = getattr(request, "user", None)
        role = (
            getattr(user, "role", None)
            or getattr(user, "portal_role", None)
            or getattr(user, "user_type", None)
        )
        if role is not None:
            md["role"] = role
    return md


def get_ai_provider_status() -> dict[str, Any]:
    endpoint, ollama_model = _ollama_config()
    rules_enabled = bool(getattr(settings, "AI_ALLOW_RULES_FALLBACK", True))
    has_live = bool(endpoint and ollama_model)
    return {
        "preference": _provider_preference(),
        "has_live_provider": has_live,
        "rules_fallback_enabled": rules_enabled,
        "ollama": {
            "configured": bool(endpoint and ollama_model),
            "endpoint": endpoint,
            "model": ollama_model or None,
        },
    }


def get_public_ai_provider_status() -> dict[str, Any]:
    """
    Return frontend-safe provider status.

    This intentionally omits provider secrets and internal connection details such
    as the Ollama endpoint URL. Frontend widgets need capability/state visibility,
    not infrastructure coordinates.
    """
    status = get_ai_provider_status()
    return {
        "preference": list(status.get("preference", [])),
        "has_live_provider": bool(status.get("has_live_provider")),
        "rules_fallback_enabled": bool(status.get("rules_fallback_enabled")),
        "providers": {
            "ollama": {
                "configured": bool(status.get("ollama", {}).get("configured")),
                "model": status.get("ollama", {}).get("model"),
                "exposure": "local",
            },
        },
    }


def generate_ai_response(
    prompt: str,
    *,
    user_query: str,
    metadata: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Return (response_text, metadata).

    Security/architecture: All AI traffic must go through the AI Gateway so:
    - provider secrets stay server-side
    - rate limiting/audit is centralized
    - task routing and fallbacks are consistent
    metadata is kept for logs/observability only and never added to prompt text.
    """
    normalized_metadata = _normalize_gateway_metadata(metadata)
    if not getattr(settings, "AI_GATEWAY_ENABLED", True):
        if _is_policy_denied(user_query):
            return (
                "Request rejected by safety policy. Please rephrase as a normal school-operation question.",
                {
                    "provider": "policy",
                    "errors": {"policy": "prompt_injection_guard"},
                    "denied": True,
                },
            )
        if bool(getattr(settings, "AI_ALLOW_RULES_FALLBACK", True)):
            return _rules_fallback(user_query), {
                "provider": "rules",
                "errors": {"gateway": "disabled"},
                "fallback": True,
                "gateway": False,
            }
        return (
            "AI is disabled and rules fallback is disabled.",
            {
                "provider": "none",
                "errors": {"gateway": "disabled"},
                "fallback": False,
                "gateway": False,
            },
        )
    try:
        from services.ai_gateway import invoke

        result, meta = invoke(
            "general_chat",
            prompt,
            user_query=user_query,
            metadata=normalized_metadata,
        )
        gateway_meta = {**meta, "gateway": True}
        if isinstance(result, str):
            return result, gateway_meta
        if meta.get("prompt_injection_blocked"):
            return (
                "Request rejected by safety policy. Please rephrase as a normal school-operation question.",
                {**gateway_meta, "denied": True},
            )
        if meta.get("budget_exceeded"):
            return (
                "AI request budget exceeded for this tenant.",
                gateway_meta,
            )
        if result is None:
            return (
                "AI providers are currently unavailable and rules fallback is disabled.",
                gateway_meta,
            )
        return str(result), gateway_meta
    except _AI_GATEWAY_INVOKE_ERRORS as e:
        logger.warning("AI gateway invoke failed: %s", e)
        if bool(getattr(settings, "AI_ALLOW_RULES_FALLBACK", True)):
            return _rules_fallback(user_query), {
                "provider": "rules",
                "errors": {"gateway": "unavailable"},
                "fallback": True,
                "gateway": True,
            }
        return (
            "AI providers are currently unavailable and rules fallback is disabled.",
            {
                "provider": "none",
                "errors": {"gateway": "unavailable"},
                "fallback": False,
                "gateway": True,
            },
        )


def get_workflow_clues(
    workflow_key: str,
    country_code: str,
    *,
    request: Any = None,
    school: Any = None,
) -> tuple[str | None, dict[str, Any]]:
    """
    World Engine: workflow setup suggestions by country. Uses AI gateway (setup_recommend) when enabled.
    Returns (suggestions_text, metadata). Use for onboarding/setup wizards.
    """
    prompt = (
        f"Brief setup suggestions for the school workflow '{workflow_key}' in country code '{country_code}'. "
        "List 3–5 short, actionable tips (local regulations, common practices, or checklist items). "
        "Keep the response under 400 words."
    )
    if not getattr(settings, "AI_GATEWAY_ENABLED", True):
        return None, {"gateway": False, "error": "disabled"}
    try:
        from services.ai_gateway import invoke

        effective_school = school or getattr(request, "school", None)
        school_id = (
            str(getattr(effective_school, "pk", None) or getattr(effective_school, "id", None))
            if effective_school is not None
            else None
        )
        user = getattr(request, "user", None)
        user_id = getattr(user, "pk", None) or getattr(user, "id", None)

        result, meta = invoke(
            "setup_recommend",
            prompt,
            user_query=prompt[:200],
            metadata=_normalize_gateway_metadata(
                {
                "request": request,
                "school": effective_school,
                "school_id": school_id,
                "tenant_id": school_id,
                "user_id": str(user_id) if user_id is not None else None,
                "country_code": country_code,
                }
            ),
        )
        text = result if isinstance(result, str) else None
        if text:
            return text.strip(), {**meta, "gateway": True}
        return None, {
            **meta,
            "gateway": True,
            "error": meta.get("error", "unavailable"),
        }
    except _AI_GATEWAY_INVOKE_ERRORS as e:
        logger.warning("Gateway get_workflow_clues failed: %s", e)
        return None, {"gateway": True, "error": "unavailable"}


def suggest_support_ticket_response(
    subject: str,
    body: str,
    *,
    country_code: str | None = None,
    school: Any = None,
    user_id: Any = None,
    role: Any = None,
) -> tuple[dict | None, dict]:
    """
    World Engine: support-ticket agent — suggest category/priority/response from ticket text.
    Optionally prepends tenant KB/FAQ excerpts (``SUPPORT_AI_KB_CONTEXT``) then calls
    AI gateway (``support_suggest``; Ollama-first). Returns (suggestions_dict, meta).
    """
    import json

    from apps.portal.support_ai_context import build_kb_context_block

    kb_block = build_kb_context_block(subject, body, school)
    core = (
        f"Support ticket — Subject: {subject[:200]}. Body: {body[:800]}.\n"
        'Respond with a short JSON only: {"category": "...", "priority": "LOW|NORMAL|HIGH|URGENT", "suggested_reply": "..."}. '
        "Keep suggested_reply under 200 words."
    )
    if kb_block:
        prompt = f"{kb_block}\n\n{core}"
    else:
        prompt = core
    if not getattr(settings, "AI_GATEWAY_ENABLED", True):
        return None, {"gateway": False, "error": "disabled"}
    text = None
    meta: dict[str, Any] = {}
    try:
        from services.ai_gateway import invoke

        md_ai = _normalize_gateway_metadata(
            {
                "country_code": country_code,
                "school": school,
                "user_id": user_id,
                "role": role,
            }
        )
        result, meta = invoke(
            "support_suggest",
            prompt,
            user_query=subject[:200],
            metadata=md_ai,
        )
        text = (
            result
            if isinstance(result, str)
            else (str(result) if result is not None else None)
        )
        meta.setdefault("gateway", True)
    except _AI_GATEWAY_INVOKE_ERRORS as e:
        logger.warning("Gateway suggest_support_ticket failed: %s", e)
        return None, {"gateway": True, "error": "unavailable"}
    if text is None:
        return None, {**meta, "error": meta.get("error", "unavailable")}
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end]), meta
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return {"suggested_reply": text.strip()[:500]}, meta
