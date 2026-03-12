"""
AI provider abstraction for sovereign/local-first execution.

Priority order is configurable and defaults to:
    ollama -> rules (local-first). Gemini is opt-in per tenant via AI_PROVIDER_PREFERENCE.

Set AI_PROVIDER_PREFERENCE to include "gemini" (e.g. "ollama,gemini,rules") only when
a tenant has explicitly approved use of the paid API.

`metadata` is intentionally not appended to model prompts so tenant identifiers
or internal IDs are not sent to external providers.

Sync vs async: Use generate_ai_response (sync) for single-turn copilot only. For bulk
or long-running (syllabus sync, bulk support suggestion, report-card remarks), use
apps.portal.tasks.generate_ai_response_async and poll cache key ai:async_result:{task_id}.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

# Local-first default: ollama then rules. Add "gemini" only when tenant has approved.
DEFAULT_PROVIDER_ORDER = ["ollama", "rules"]
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


def _gemini_model() -> str:
    return (
        getattr(settings, "GEMINI_MODEL", None)
        or os.environ.get("GEMINI_MODEL")
        or "gemini-pro"
    ).strip()


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


def _call_gemini(prompt: str) -> str | None:
    api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return None
    model = _gemini_model()
    if not model:
        return None
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 500,
        },
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ],
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_request_timeout_seconds()) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError:
        return None
    except Exception:
        logger.exception("Gemini call failed")
        return None
    return (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text")
        or None
    )


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


def get_ai_provider_status() -> dict[str, Any]:
    endpoint, ollama_model = _ollama_config()
    gemini_model = _gemini_model()
    gemini_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    rules_enabled = bool(
        getattr(settings, "AI_ALLOW_RULES_FALLBACK", True)
    )
    has_live = bool(endpoint and ollama_model) or bool(gemini_key)
    return {
        "preference": _provider_preference(),
        "has_live_provider": has_live,
        "rules_fallback_enabled": rules_enabled,
        "ollama": {
            "configured": bool(endpoint and ollama_model),
            "endpoint": endpoint,
            "model": ollama_model or None,
        },
        "gemini": {
            "configured": bool(gemini_key),
            "model": gemini_model or None,
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
            "gemini": {
                "configured": bool(status.get("gemini", {}).get("configured")),
                "model": status.get("gemini", {}).get("model"),
                "exposure": "external",
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
    _ = metadata or {}
    if _is_policy_denied(user_query):
        return (
            "Request rejected by safety policy. Please rephrase as a normal school-operation question.",
            {
                "provider": "policy",
                "errors": {"policy": "prompt_injection_guard"},
                "denied": True,
            },
        )
    if not getattr(settings, "AI_GATEWAY_ENABLED", True):
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
            metadata={**_},
        )
        text = result if isinstance(result, str) else str(result)
        return text, {**meta, "gateway": True}
    except Exception as e:
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


def get_workflow_clues(workflow_key: str, country_code: str) -> tuple[str | None, dict[str, Any]]:
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

        result, meta = invoke(
            "setup_recommend",
            prompt,
            user_query=prompt[:200],
            metadata={"country_code": country_code},
        )
        text = result if isinstance(result, str) else None
        if text:
            return text.strip(), {**meta, "gateway": True}
        return None, {**meta, "gateway": True, "error": meta.get("error", "unavailable")}
    except Exception as e:
        logger.warning("Gateway get_workflow_clues failed: %s", e)
        return None, {"gateway": True, "error": "unavailable"}


def suggest_support_ticket_response(
    subject: str,
    body: str,
    *,
    country_code: str | None = None,
    school: Any = None,
) -> tuple[dict | None, dict]:
    """
    World Engine: FAISS/Llama support-ticket agent — suggest category/priority/response from ticket text.
    Uses AI gateway (support_suggest) when enabled. Returns (suggestions_dict, meta).
    """
    prompt = (
        f"Support ticket — Subject: {subject[:200]}. Body: {body[:800]}.\n"
        "Respond with a short JSON only: {\"category\": \"...\", \"priority\": \"LOW|NORMAL|HIGH|URGENT\", \"suggested_reply\": \"...\"}. "
        "Keep suggested_reply under 200 words."
    )
    if not getattr(settings, "AI_GATEWAY_ENABLED", True):
        return None, {"gateway": False, "error": "disabled"}
    text = None
    meta: dict[str, Any] = {}
    try:
        from services.ai_gateway import invoke

        result, meta = invoke(
            "support_suggest",
            prompt,
            user_query=subject[:200],
            metadata={"country_code": country_code, "school": school},
        )
        text = result if isinstance(result, str) else (str(result) if result is not None else None)
        meta.setdefault("gateway", True)
    except Exception as e:
        logger.warning("Gateway suggest_support_ticket failed: %s", e)
        return None, {"gateway": True, "error": "unavailable"}
    if text is None:
        return None, {**meta, "error": meta.get("error", "unavailable")}
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end]), meta
    except Exception:
        pass
    return {"suggested_reply": text.strip()[:500]}, meta
