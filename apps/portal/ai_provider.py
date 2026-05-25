"""
AI provider abstraction for sovereign/local-first execution.

Priority order is configurable and defaults to:
    ollama -> rules (local-first on edge/hub).

All generative chat goes through ``services.ai_gateway.invoke`` when
``AI_GATEWAY_ENABLED`` is true. Gateway tier chains follow ``RMC_DEPLOYMENT_PROFILE``
(see ``services.ai_deployment_posture``): **online** Render SaaS prefers LiteLLM
when ``LITELLM_PROXY_URL`` is set, then Ollama, then rules; **edge** hubs prefer
Ollama then rules. This module supplies reachability probes and operator-facing status.

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

from services.ai_helpers import normalize_gateway_metadata

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


def _ollama_auto_discover_enabled() -> bool:
    if hasattr(settings, "OLLAMA_AUTO_DISCOVER"):
        return bool(getattr(settings, "OLLAMA_AUTO_DISCOVER"))
    raw = os.environ.get("OLLAMA_AUTO_DISCOVER", "1")
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _wsl_windows_host_ip() -> str | None:
    """WSL2: /etc/resolv.conf nameserver is usually the Windows host running Ollama."""
    try:
        from pathlib import Path

        resolv = Path("/etc/resolv.conf")
        if not resolv.is_file():
            return None
        for line in resolv.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line.startswith("nameserver "):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            ip = parts[1].strip()
            if ip and ip not in {"127.0.0.1", "::1"}:
                return ip
    except OSError:
        return None
    return None


def _ollama_env_overrides() -> tuple[str, str]:
    endpoint = (
        getattr(settings, "OLLAMA_ENDPOINT", None)
        or os.environ.get("OLLAMA_ENDPOINT")
        or ""
    ).strip()
    base_url = (
        getattr(settings, "OLLAMA_BASE_URL", None)
        or os.environ.get("OLLAMA_BASE_URL")
        or ""
    ).strip().rstrip("/")
    return endpoint, base_url


def _base_from_endpoint(endpoint: str) -> str:
    import urllib.parse

    parsed = urllib.parse.urlparse(endpoint)
    if parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    return ""


def ollama_base_candidates() -> list[str]:
    """
    Ordered hosts to try when auto-discovering Ollama.

    Covers Windows native (127.0.0.1), Docker Desktop (host.docker.internal),
    and WSL Django + Windows Ollama (resolv.conf gateway).
    """
    endpoint, base_url = _ollama_env_overrides()
    candidates: list[str] = []
    for raw in (base_url, _base_from_endpoint(endpoint) if endpoint else ""):
        item = (raw or "").strip().rstrip("/")
        if item and item not in candidates:
            candidates.append(item)

    for host in (
        "http://127.0.0.1:11434",
        "http://localhost:11434",
        "http://host.docker.internal:11434",
    ):
        if host not in candidates:
            candidates.append(host)

    wsl_host = _wsl_windows_host_ip()
    if wsl_host:
        wsl_base = f"http://{wsl_host}:11434"
        if wsl_base not in candidates:
            candidates.append(wsl_base)

    extra = (
        getattr(settings, "OLLAMA_BASE_URL_CANDIDATES", None)
        or os.environ.get("OLLAMA_BASE_URL_CANDIDATES")
        or ""
    )
    for part in str(extra).split(","):
        item = part.strip().rstrip("/")
        if item and item not in candidates:
            candidates.append(item)
    return candidates


def _probe_ollama_base(base_url: str, *, timeout_sec: float = 2.0) -> tuple[bool, int | None]:
    import time as _t
    import urllib.request

    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        t0 = _t.monotonic()
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:  # noqa: S310
            ok = 200 <= resp.status < 500
        if not ok:
            return False, None
        return True, int((_t.monotonic() - t0) * 1000)
    except _AI_GATEWAY_INVOKE_ERRORS:
        return False, None
    except Exception:  # noqa: BLE001
        return False, None


def _pick_reachable_ollama_base(candidates: list[str]) -> tuple[str | None, int | None, str | None]:
    for base in candidates:
        ok, latency_ms = _probe_ollama_base(base)
        if ok:
            return base, latency_ms, base
    return None, None, None


def _connection_from_base(
    base_url: str,
    *,
    model: str,
    discovery_source: str | None = None,
) -> dict[str, Any]:
    base = base_url.strip().rstrip("/")
    return {
        "base_url": base,
        "generate_endpoint": f"{base}/api/generate",
        "model": model,
        "configured": bool(base and model),
        "discovery_source": discovery_source or base,
        "auto_discover": _ollama_auto_discover_enabled(),
    }


def resolve_ollama_connection(*, force_refresh: bool = False) -> dict[str, Any]:
    """
    Single resolver for Ollama host + generate URL + model.

    With ``OLLAMA_AUTO_DISCOVER=1`` (default), probes common dev hosts in order
    (env override first, then 127.0.0.1, localhost, host.docker.internal, WSL gateway)
    and uses the first reachable base. Pin a host with ``OLLAMA_BASE_URL`` or
    ``OLLAMA_ENDPOINT`` only — set ``OLLAMA_AUTO_DISCOVER=0`` to disable scanning.
    """
    from django.core.cache import cache

    model = (
        getattr(settings, "OLLAMA_MODEL", None)
        or os.environ.get("OLLAMA_MODEL")
        or "llama3"
    ).strip()
    candidates = ollama_base_candidates()
    default_base = candidates[0] if candidates else "http://127.0.0.1:11434"

    if not _ollama_auto_discover_enabled():
        return _connection_from_base(default_base, model=model, discovery_source="pinned")

    cache_key = "ai:ollama:resolved-connection"
    if not force_refresh:
        try:
            cached = cache.get(cache_key)
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            cached = None
        if isinstance(cached, dict) and cached.get("base_url"):
            cached_model = str(cached.get("model") or model).strip() or model
            return _connection_from_base(
                str(cached["base_url"]),
                model=cached_model,
                discovery_source=str(cached.get("discovery_source") or cached["base_url"]),
            )

    picked, _latency_ms, source = _pick_reachable_ollama_base(candidates)
    base_url = picked or default_base
    conn = _connection_from_base(
        base_url,
        model=model,
        discovery_source=source or ("unreachable-default" if not picked else source),
    )
    ttl = int(getattr(settings, "AI_HEALTH_CACHE_TTL_SECONDS", 60) or 60)
    try:
        cache.set(
            cache_key,
            {
                "base_url": conn["base_url"],
                "model": model,
                "discovery_source": conn.get("discovery_source"),
            },
            ttl,
        )
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        pass
    if picked:
        logger.debug(
            "ollama auto-discover: using %s (candidates=%s)",
            conn["base_url"],
            len(candidates),
        )
    else:
        logger.warning(
            "ollama auto-discover: no reachable host among %s; defaulting to %s",
            candidates,
            conn["base_url"],
        )
    return conn


def ollama_require_live() -> bool:
    """
    When true, the product must not serve rules-template \"AI answers\" (guided fallback).

    Default: on in production / cloud deploy; off in local DEBUG and during tests.
    """
    if hasattr(settings, "OLLAMA_REQUIRE_LIVE"):
        return bool(getattr(settings, "OLLAMA_REQUIRE_LIVE"))
    raw = os.environ.get("OLLAMA_REQUIRE_LIVE", "0")
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def ai_rules_fallback_allowed() -> bool:
    """Rules tier is allowed only when live Ollama is not mandatory or explicit dev fallback is on."""
    if ollama_require_live():
        return False
    return bool(getattr(settings, "AI_ALLOW_RULES_FALLBACK", True))


def log_ai_startup_posture(
    *,
    health: dict[str, Any],
    conn: dict[str, Any] | None = None,
) -> None:
    """Emit a single startup line matching the provider that answered the reachability probe."""
    conn = conn or {}
    provider = str(health.get("provider") or "none").strip().lower()
    reachable = bool(health.get("reachable"))
    profile = str(health.get("deployment_profile") or "online")

    if reachable and provider == "litellm":
        logger.info(
            "AI startup: live cloud AI (profile=%s, provider=litellm)",
            profile,
        )
        return
    if reachable and provider == "ollama":
        logger.info(
            "AI startup: live Ollama at %s (discovery=%s)",
            conn.get("base_url"),
            conn.get("discovery_source"),
        )
        return
    if ollama_require_live():
        logger.error(
            "AI startup: OLLAMA_REQUIRE_LIVE=1 but no live AI provider (ollama base=%s). "
            "Assistants will return 'live AI unavailable' (not template fallback). "
            "Run: python scripts/verify_ollama_live.py --strict --invoke",
            conn.get("base_url"),
        )
        return
    if ai_rules_fallback_allowed():
        logger.warning(
            "AI startup: no live AI provider; intelligent grounded fallback is active "
            "(profile=%s).",
            profile,
        )


def invalidate_ollama_connection_cache() -> None:
    """Clear cached auto-discovered base (e.g. after starting ``ollama serve``)."""
    try:
        from django.core.cache import cache

        cache.delete("ai:ollama:resolved-connection")
        cache.delete("ai:health:provider-reachability")
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        pass


def _ollama_config() -> tuple[str, str]:
    conn = resolve_ollama_connection()
    return conn["generate_endpoint"], conn["model"]


def _call_ollama(prompt: str, metadata: dict[str, Any] | None = None) -> str | None:
    """
    Single Ollama entry point: delegates to OllamaInferenceService (region, dossier, cache, fallback).
    Resolves school/tenant/country from metadata; no direct HTTP here (F.1).
    """
    from services.ollama_runtime import ensure_ollama_reachable

    ensure_ollama_reachable()
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


def get_ai_provider_status() -> dict[str, Any]:
    from services.ai_deployment_posture import is_litellm_configured, normalize_deployment_profile

    conn = resolve_ollama_connection()
    rules_enabled = bool(getattr(settings, "AI_ALLOW_RULES_FALLBACK", True))
    configured = bool(conn.get("configured"))
    litellm = is_litellm_configured()
    return {
        "preference": _provider_preference(),
        "deployment_profile": normalize_deployment_profile(),
        "ollama_configured": configured,
        "litellm_configured": litellm,
        # Back-compat: env configured for any live tier — use get_public_ai_provider_status for reachability.
        "has_live_provider": litellm or configured,
        "rules_fallback_enabled": rules_enabled,
        "ollama": {
            "configured": configured,
            "endpoint": conn.get("generate_endpoint"),
            "model": conn.get("model") or None,
        },
    }


def get_public_ai_provider_status(*, include_health: bool = True) -> dict[str, Any]:
    """
    Return frontend-safe provider status.

    This intentionally omits provider secrets and internal connection details such
    as the Ollama endpoint URL. Frontend widgets need capability/state visibility,
    not infrastructure coordinates.

    When ``include_health`` is true (default), ``has_live_provider`` means a live
    tier answered a reachability probe (LiteLLM on online/hybrid, or Ollama on edge).
    """
    from services.ai_deployment_posture import enrich_public_provider_status

    status = get_ai_provider_status()
    configured = bool(status.get("ollama_configured"))
    health: dict[str, Any] = {}
    if include_health:
        health = probe_ai_provider_reachable()
    reachable = bool(health.get("reachable"))
    base = {
        "preference": list(status.get("preference", [])),
        "ollama_configured": configured,
        "has_live_provider": reachable,
        "reachable": reachable,
        "fallback_active": bool(health.get("fallback_active")),
        "degraded": bool(health.get("degraded")) if include_health else (not reachable),
        "latency_ms": health.get("latency_ms"),
        "rules_fallback_enabled": bool(status.get("rules_fallback_enabled")),
        "providers": {
            "ollama": {
                "configured": configured,
                "model": status.get("ollama", {}).get("model"),
                "exposure": "local",
            },
        },
    }
    return enrich_public_provider_status(base, health=health if include_health else None)


def probe_ai_provider_reachable() -> dict[str, Any]:
    """
    Lightweight reachability probe — does the configured provider answer a TCP ping?

    Result is cached for AI_HEALTH_CACHE_TTL seconds (default 60) so the copilot UI
    can surface degraded mode without hammering backends. Returns reachability,
    deployment profile, posture fields, and provider id (`litellm` | `ollama` | `rules` | `none`).
    """
    from datetime import datetime, timezone

    from django.core.cache import cache

    from services.ai_deployment_posture import (
        build_posture_fields,
        is_litellm_configured,
        normalize_deployment_profile,
        probe_litellm_reachable,
    )

    cache_key = "ai:health:provider-reachability"
    cached = None
    try:
        cached = cache.get(cache_key)
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        cached = None
    if cached is not None:
        return cached

    status = get_ai_provider_status()
    preference = status.get("preference", [])
    rules_enabled = bool(status.get("rules_fallback_enabled"))
    profile = normalize_deployment_profile()
    result: dict[str, Any] = {
        "reachable": False,
        "provider": "none",
        "latency_ms": None,
        "fallback_active": False,
        "degraded": True,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "deployment_profile": profile,
        "litellm_configured": is_litellm_configured(),
    }

    if profile in {"online", "hybrid"} and is_litellm_configured():
        ok, latency_ms = probe_litellm_reachable()
        if ok:
            result.update({
                "reachable": True,
                "provider": "litellm",
                "latency_ms": latency_ms,
                "degraded": False,
            })

    if not result["reachable"] and "ollama" in preference and status.get("ollama", {}).get("configured"):
        conn = resolve_ollama_connection()
        ok, latency_ms = _probe_ollama_base(str(conn.get("base_url") or ""))
        if ok:
            result.update({
                "reachable": True,
                "provider": "ollama",
                "latency_ms": latency_ms,
                "degraded": False,
                "ollama_discovery_source": conn.get("discovery_source"),
            })
        elif _ollama_auto_discover_enabled():
            invalidate_ollama_connection_cache()
            conn = resolve_ollama_connection(force_refresh=True)
            ok, latency_ms = _probe_ollama_base(str(conn.get("base_url") or ""))
            if ok:
                result.update({
                    "reachable": True,
                    "provider": "ollama",
                    "latency_ms": latency_ms,
                    "degraded": False,
                    "ollama_discovery_source": conn.get("discovery_source"),
                })

    if not result["reachable"] and rules_enabled:
        result.update({
            "provider": "rules",
            "fallback_active": True,
            "degraded": True,
        })

    result.update(
        build_posture_fields(
            deployment_profile=profile,
            reachable=bool(result.get("reachable")),
            provider=str(result.get("provider") or "none"),
            litellm_configured=is_litellm_configured(),
            ollama_configured=bool(status.get("ollama_configured")),
            rules_fallback_enabled=rules_enabled,
            fallback_active=bool(result.get("fallback_active")),
        )
    )

    ttl = int(getattr(settings, "AI_HEALTH_CACHE_TTL_SECONDS", 60) or 60)
    try:
        cache.set(cache_key, result, ttl)
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        pass
    return result


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
    normalized_metadata = normalize_gateway_metadata(metadata)
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
        if ai_rules_fallback_allowed():
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
        if ai_rules_fallback_allowed():
            return _rules_fallback(user_query), {
                "provider": "rules",
                "errors": {"gateway": "unavailable"},
                "fallback": True,
                "gateway": True,
            }
        from services.ai_unavailable import ollama_unavailable_message

        return (
            ollama_unavailable_message(),
            {
                "provider": "none",
                "errors": {"gateway": "unavailable"},
                "fallback": False,
                "gateway": True,
                "live_ai_unavailable": True,
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
            metadata=normalize_gateway_metadata(
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

        md_ai = normalize_gateway_metadata(
            {
                "country_code": country_code,
                "school": school,
                "school_id": getattr(school, "pk", None) if school is not None else None,
                "tenant_id": getattr(school, "pk", None) if school is not None else None,
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
