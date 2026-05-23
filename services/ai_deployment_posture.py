"""
Deployment-profile-aware AI posture for RunMyCampus.

Maps ``RMC_DEPLOYMENT_PROFILE`` (online | edge | hybrid) to gateway tier chains and
operator-facing status labels. Render SaaS (online) prefers cloud LiteLLM when
configured; edge/hybrid LAN hubs prefer on-prem Ollama.

See docs/LOCAL_HUB_MODE.md.
"""

from __future__ import annotations

import logging
import os
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

VALID_PROFILES = frozenset({"online", "edge", "hybrid"})

# Option A (Render SaaS default): one cloud model + rules fallback — see docs/AI_DEPLOYMENT_POSTURE.md
DEFAULT_LITELLM_MODEL = "gpt-5.4-mini"
DEFAULT_OPENAI_API_BASE = "https://api.openai.com"

_ONLINE_CLOUD_CHAIN = ["litellm", "ollama", "rules"]
_ONLINE_LOCAL_CHAIN = ["ollama", "rules"]
_EDGE_CHAIN = ["ollama", "rules"]
_HYBRID_CHAIN = ["litellm", "ollama", "rules"]


def normalize_deployment_profile(raw: str | None = None) -> str:
    value = (
        raw
        or getattr(settings, "RMC_DEPLOYMENT_PROFILE", None)
        or os.environ.get("RMC_DEPLOYMENT_PROFILE", "online")
        or "online"
    )
    profile = str(value).strip().lower() or "online"
    if profile not in VALID_PROFILES:
        return "online"
    return profile


def _setting_str(
    name: str,
    *,
    default: str = "",
    strip_trailing_slash: bool = False,
) -> str:
    """
    Read a string Django setting.

    When the attribute exists on ``settings`` (including ``@override_settings``),
    honor it even if empty — do not fall back to ``os.environ`` (tests and runtime
    overrides must not leak host env into isolated cases).
    """
    if hasattr(settings, name):
        raw = getattr(settings, name, default)
    else:
        raw = os.environ.get(name, default)
    value = str(raw if raw is not None else default).strip()
    if strip_trailing_slash:
        value = value.rstrip("/")
    return value


def litellm_proxy_url() -> str:
    return _setting_str("LITELLM_PROXY_URL", strip_trailing_slash=True)


def litellm_model(*, model_key: str | None = None) -> str:
    if model_key:
        return str(model_key).strip()
    configured = _setting_str("LITELLM_MODEL")
    return configured or DEFAULT_LITELLM_MODEL


def litellm_api_key() -> str:
    return _setting_str("LITELLM_API_KEY")


def is_litellm_configured() -> bool:
    return bool(litellm_proxy_url())


def default_tier_chain_for_profile(profile: str | None = None) -> list[str]:
    """Default gateway tier order for a deployment profile (before per-task overrides)."""
    p = normalize_deployment_profile(profile)
    if p == "online":
        return list(_ONLINE_CLOUD_CHAIN if is_litellm_configured() else _ONLINE_LOCAL_CHAIN)
    if p == "hybrid":
        return list(_HYBRID_CHAIN if is_litellm_configured() else _EDGE_CHAIN)
    return list(_EDGE_CHAIN)


def _parse_custom_task_tiers(raw: Any) -> dict[str, list[str]] | None:
    if not raw:
        return None
    if isinstance(raw, dict):
        out: dict[str, list[str]] = {}
        for key, value in raw.items():
            if isinstance(value, list):
                out[str(key)] = [str(x).lower() for x in value]
            elif isinstance(value, str):
                out[str(key)] = [
                    x.strip().lower() for x in value.split(",") if x.strip()
                ]
        return out or None
    return None


def merge_effective_task_tiers(
    custom_override: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    """
    Build per-task tier map: profile defaults merged with ``AI_GATEWAY_TASK_TIERS``.
    """
    from services.ai_gateway import DEFAULT_TASK_TIERS

    chain = default_tier_chain_for_profile()
    out: dict[str, list[str]] = {}
    for task_type, _default in DEFAULT_TASK_TIERS.items():
        key = task_type.value if hasattr(task_type, "value") else str(task_type)
        out[key] = list(chain)

    custom = custom_override
    if custom is None:
        custom = _parse_custom_task_tiers(
            getattr(settings, "AI_GATEWAY_TASK_TIERS", None)
        )
    if custom:
        for key, tiers in custom.items():
            if tiers:
                out[key] = list(tiers)
    return out


def _litellm_models_url(proxy_url: str) -> str:
    base = proxy_url.rstrip("/")
    if "/v1/" in base or base.endswith("/v1"):
        return f"{base.rstrip('/')}/models"
    return f"{base}/v1/models"


def probe_litellm_reachable(timeout_sec: float = 4.0) -> tuple[bool, int | None]:
    """
    Lightweight OpenAI-compatible models probe (no prompt spend).
    """
    proxy = litellm_proxy_url()
    if not proxy:
        return False, None
    url = _litellm_models_url(proxy)
    if not url.startswith("http"):
        url = f"https://{url}"
    headers: dict[str, str] = {"Accept": "application/json"}
    api_key = litellm_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        import time

        start = time.perf_counter()
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            resp.read(4096)
        latency_ms = int((time.perf_counter() - start) * 1000)
        return True, latency_ms
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.debug("LiteLLM models probe failed: %s", exc)
        return False, None


def operator_setup_kind(profile: str | None = None) -> str:
    """Template hint: render_cloud | edge_ollama | hybrid_cloud."""
    p = normalize_deployment_profile(profile)
    if p == "online":
        return "render_cloud"
    if p == "hybrid":
        return "hybrid_cloud"
    return "edge_ollama"


def build_posture_fields(
    *,
    deployment_profile: str,
    reachable: bool,
    provider: str,
    litellm_configured: bool,
    ollama_configured: bool,
    rules_fallback_enabled: bool,
    fallback_active: bool,
) -> dict[str, Any]:
    """
    UI-safe posture snapshot (no secrets / internal URLs).
    """
    profile = normalize_deployment_profile(deployment_profile)
    provider_name = str(provider or "none").strip().lower()
    tier_chain = default_tier_chain_for_profile(profile)

    if reachable and provider_name == "litellm":
        posture_mode = "live_cloud"
        posture_label = "Live — cloud AI"
        live_provider_kind = "cloud"
    elif reachable and provider_name == "ollama":
        posture_mode = "live_local"
        posture_label = "Live — Ollama on server"
        live_provider_kind = "ollama"
    elif rules_fallback_enabled and (fallback_active or not reachable):
        posture_mode = "guided"
        posture_label = "Guided — help center & maps"
        live_provider_kind = "rules"
    else:
        posture_mode = "unavailable"
        posture_label = "AI unavailable — check server config"
        live_provider_kind = "none"

    return {
        "deployment_profile": profile,
        "litellm_configured": litellm_configured,
        "ollama_configured": ollama_configured,
        "posture_mode": posture_mode,
        "posture_label": posture_label,
        "live_provider_kind": live_provider_kind,
        "gateway_tier_chain": tier_chain,
        "operator_setup_kind": operator_setup_kind(profile),
        "ai_needs_network": True,
    }


def enrich_public_provider_status(
    base: dict[str, Any],
    *,
    health: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach deployment posture fields to ``get_public_ai_provider_status`` payload."""
    health = health or {}
    profile = normalize_deployment_profile()
    litellm_configured = is_litellm_configured()
    ollama_configured = bool(base.get("ollama_configured"))
    reachable = bool(health.get("reachable", base.get("reachable")))
    provider = str(health.get("provider") or "none")
    rules_enabled = bool(base.get("rules_fallback_enabled"))
    fallback_active = bool(health.get("fallback_active", base.get("fallback_active")))

    posture = build_posture_fields(
        deployment_profile=profile,
        reachable=reachable,
        provider=provider,
        litellm_configured=litellm_configured,
        ollama_configured=ollama_configured,
        rules_fallback_enabled=rules_enabled,
        fallback_active=fallback_active,
    )

    providers = dict(base.get("providers") or {})
    if litellm_configured:
        providers["litellm"] = {
            "configured": True,
            "model": litellm_model(),
            "exposure": "cloud",
        }

    enriched = {**base, **posture, "providers": providers}
    if reachable:
        enriched["has_live_provider"] = True
        enriched["reachable"] = True
        enriched["degraded"] = False
    elif rules_enabled and fallback_active:
        enriched["has_live_provider"] = False
        enriched["degraded"] = True
    return enriched
