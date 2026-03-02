"""
AI provider abstraction for sovereign/local-first execution.

Priority order is configurable and defaults to:
    ollama -> rules (local-first). Gemini is opt-in per tenant via AI_PROVIDER_PREFERENCE.

Set AI_PROVIDER_PREFERENCE to include "gemini" (e.g. "ollama,gemini,rules") only when
a tenant has explicitly approved use of the paid API.

`metadata` is intentionally not appended to model prompts so tenant identifiers
or internal IDs are not sent to external providers.
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


def _call_ollama(prompt: str) -> str | None:
    endpoint, model = _ollama_config()
    if not endpoint or not model:
        return None
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_request_timeout_seconds()) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError:
        return None
    except Exception:
        logger.exception("Ollama call failed")
        return None

    text = str(body.get("response") or "").strip()
    return text or None


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


def generate_ai_response(
    prompt: str,
    *,
    user_query: str,
    metadata: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Return (response_text, metadata).
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
    errors: dict[str, str] = {}
    for provider in _provider_preference():
        if provider == "ollama":
            text = _call_ollama(prompt)
            if text:
                return text, {"provider": "ollama", "errors": errors}
            errors["ollama"] = "unavailable"
            continue
        if provider == "gemini":
            text = _call_gemini(prompt)
            if text:
                return text, {"provider": "gemini", "errors": errors}
            errors["gemini"] = "unavailable"
            continue
        if provider == "rules":
            if not bool(getattr(settings, "AI_ALLOW_RULES_FALLBACK", True)):
                errors["rules"] = "disabled"
                continue
            return _rules_fallback(user_query), {
                "provider": "rules",
                "errors": errors,
                "fallback": True,
            }
    if bool(getattr(settings, "AI_ALLOW_RULES_FALLBACK", True)):
        return _rules_fallback(user_query), {"provider": "rules", "errors": errors, "fallback": True}
    return (
        "AI providers are currently unavailable and rules fallback is disabled.",
        {
            "provider": "none",
            "errors": errors,
            "fallback": False,
        },
    )
