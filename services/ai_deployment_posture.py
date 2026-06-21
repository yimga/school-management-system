"""
Deployment-profile-aware AI posture for RunMyCampus.

Maps ``RMC_DEPLOYMENT_PROFILE`` (online | edge | hybrid) to gateway tier chains and
operator-facing status labels. Render SaaS (online) prefers cloud LiteLLM when
configured; edge/hybrid LAN hubs prefer on-prem Ollama.

See docs/LOCAL_HUB_MODE.md.
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


# --- AI mode (operator default + per-tenant override) -----------------------
# A configurable, user-facing switch layered ON TOP of the deployment profile.
# Operators set a platform default (RuntimeDefaults.ai_mode); tenants may override
# per-school. Resolution flows through the existing SiteSettings cascade, so the
# tenant override transparently wins over the platform default.
VALID_AI_MODES = ("auto", "cloud", "local")


def normalize_ai_mode(raw: str | None) -> str:
    """Coerce any stored value to one of VALID_AI_MODES; blank/unknown -> 'auto'."""
    value = str(raw or "").strip().lower()
    return value if value in VALID_AI_MODES else "auto"


def ai_mode_to_allowed_backends(mode: str | None) -> list[str] | None:
    """Translate an AI mode into a gateway ``allowed_backends`` tier filter.

    - ``auto``  -> None (no filter; the deployment profile decides)
    - ``cloud`` -> prefer the cloud gateway, then on-device, then rules
    - ``local`` -> on-device only (Ollama -> rules); data never leaves the box

    ``rules`` always stays in the chain so the call still degrades to the
    deterministic guided layer instead of failing when no model answers.
    """
    m = normalize_ai_mode(mode)
    if m == "cloud":
        return ["litellm", "ollama", "rules"]
    if m == "local":
        return ["ollama", "rules"]
    return None  # auto -> profile default


def resolve_effective_ai_mode(school: Any = None) -> str:
    """Effective AI mode for a school.

    The per-tenant override wins over the platform default — both live on the
    ``ai_mode`` first-class SiteSettings field, which the config cascade already
    resolves tenant-over-platform. Blank/unset -> ``auto``. Fails safe to ``auto``
    on any resolution error so AI never hard-breaks on a config read.
    """
    try:
        from apps.siteconfig.config_service import get_effective_site_settings

        site = get_effective_site_settings(school=school)
        return normalize_ai_mode(getattr(site, "ai_mode", None))
    except Exception:  # noqa: BLE001 — config read is best-effort; default to auto
        return "auto"


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


def _litellm_probe_timeout() -> float:
    """Probe timeout in seconds (LITELLM_PROBE_TIMEOUT_SECONDS, default 4.0).

    Env-tunable so a slow / resource-starved worker does not false-flag a
    healthy cloud provider as down on a single timed-out probe.
    """
    raw = _setting_str("LITELLM_PROBE_TIMEOUT_SECONDS")
    if raw:
        try:
            return max(1.0, min(float(raw), 30.0))
        except (TypeError, ValueError):
            pass
    return 4.0


def litellm_deep_probe_enabled() -> bool:
    """When on, the health probe issues a 1-token completion — the only definitive
    proof that *chat* works (catches wrong-model http_404 / bad-key http_401 that a
    models-list probe cannot). Default off to keep the health endpoint cheap and
    fast on constrained workers (``LITELLM_HEALTH_DEEP_PROBE``).
    """
    return _setting_str("LITELLM_HEALTH_DEEP_PROBE").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _litellm_headers() -> dict[str, str]:
    headers: dict[str, str] = {"Accept": "application/json"}
    api_key = litellm_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _litellm_listed_models(
    proxy: str, headers: dict[str, str], timeout_sec: float
) -> tuple[bool, set[str], str | None]:
    """GET /v1/models. Returns (endpoint_ok, model_ids, error).

    error: ``http_<code>`` for a definitive HTTP rejection, ``timeout`` for a
    network/timeout blip, or ``None`` on success. An unparseable list fails open
    (endpoint answered) so a proxy with a non-standard catalog is not penalised.
    """
    url = _litellm_models_url(proxy)
    if not url.startswith("http"):
        url = f"https://{url}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        return False, set(), f"http_{exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.debug("LiteLLM models probe failed: %s", exc)
        return False, set(), "timeout"
    ids: set[str] = set()
    try:
        body = json.loads(raw.decode("utf-8", errors="ignore"))
        for item in body.get("data") or []:
            mid = str(item.get("id") or "").strip()
            if mid:
                ids.add(mid)
    except (ValueError, AttributeError, TypeError):
        return True, set(), None  # answered but unparseable → fail open
    return True, ids, None


def _litellm_completion_probe(
    proxy: str, headers: dict[str, str], model: str, timeout_sec: float
) -> tuple[bool, str | None]:
    """1-token chat completion — definitive proof the configured model is callable."""
    base = proxy.rstrip("/")
    url = (
        f"{base}/v1/chat/completions"
        if "/v1/" not in base
        else f"{base}/chat/completions"
    )
    if not url.startswith("http"):
        url = f"https://{url}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_completion_tokens": 1,
    }
    post_headers = {**headers, "Content-Type": "application/json"}
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=post_headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            resp.read(512)
        return True, None
    except urllib.error.HTTPError as exc:
        return False, f"http_{exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.debug("LiteLLM completion probe failed: %s", exc)
        return False, "timeout"


def diagnose_litellm_posture(timeout_sec: float | None = None) -> dict[str, Any]:
    """Honest cloud-AI posture: distinguishes 'endpoint up' from 'chat actually works'.

    Returns ``{reachable, latency_ms, error, model, model_listed, stage}`` where
    ``error`` is one of ``None | not_configured | timeout | http_<code> |
    model_not_listed``. A models-list probe alone can be green while real
    completions 404 (wrong model) or 401 (bad key) — this surfaces that gap so the
    operator UI stops claiming "Live · cloud AI" for a provider that cannot answer.
    """
    proxy = litellm_proxy_url()
    model = litellm_model()
    if not proxy:
        return {
            "reachable": False,
            "latency_ms": None,
            "error": "not_configured",
            "model": model,
            "model_listed": False,
            "stage": "config",
        }
    timeout = timeout_sec if timeout_sec is not None else _litellm_probe_timeout()
    headers = _litellm_headers()

    import time

    start = time.perf_counter()
    endpoint_ok, model_ids, models_err = _litellm_listed_models(proxy, headers, timeout)
    latency_ms = int((time.perf_counter() - start) * 1000)
    if not endpoint_ok:
        return {
            "reachable": False,
            "latency_ms": None,
            "error": models_err or "timeout",
            "model": model,
            "model_listed": False,
            "stage": "models",
        }

    # A definitive catalog that omits the configured model means chat will 404.
    model_listed = (not model_ids) or (model in model_ids)
    if not model_listed:
        return {
            "reachable": False,
            "latency_ms": latency_ms,
            "error": "model_not_listed",
            "model": model,
            "model_listed": False,
            "stage": "model",
        }

    if litellm_deep_probe_enabled():
        ok, deep_err = _litellm_completion_probe(proxy, headers, model, timeout)
        if not ok:
            return {
                "reachable": False,
                "latency_ms": latency_ms,
                "error": deep_err,
                "model": model,
                "model_listed": True,
                "stage": "completion",
            }

    return {
        "reachable": True,
        "latency_ms": latency_ms,
        "error": None,
        "model": model,
        "model_listed": True,
        "stage": "ok",
    }


def probe_litellm_reachable(timeout_sec: float | None = None) -> tuple[bool, int | None]:
    """Back-compat 2-tuple reachability wrapper around :func:`diagnose_litellm_posture`."""
    diag = diagnose_litellm_posture(timeout_sec=timeout_sec)
    return bool(diag.get("reachable")), diag.get("latency_ms")


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
    provider_error: str | None = None,
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
        "provider_error": provider_error,
        "provider_error_hint": litellm_error_hint(provider_error),
    }


def litellm_error_hint(error: str | None) -> str:
    """Operator-facing, secret-free explanation of a LiteLLM posture error code."""
    if not error:
        return ""
    if error == "not_configured":
        return "Set LITELLM_PROXY_URL (and LITELLM_API_KEY) on the server to enable cloud AI."
    if error == "model_not_listed":
        return (
            f"The configured model ({litellm_model()}) is not offered by this "
            "endpoint. Set LITELLM_MODEL to a model your key can call."
        )
    if error in ("http_401", "http_403"):
        return "LITELLM_API_KEY is missing or not authorised for this endpoint."
    if error == "http_404":
        return (
            f"The endpoint rejected the model ({litellm_model()}) as unknown. "
            "Fix LITELLM_MODEL or LITELLM_PROXY_URL."
        )
    if error == "http_429":
        return "The cloud provider is rate-limiting requests; try again shortly."
    if error.startswith("http_5"):
        return "The cloud provider returned a server error; it may be temporarily down."
    if error == "timeout":
        return (
            "The provider did not answer within the probe window. On a slow host, "
            "raise LITELLM_PROBE_TIMEOUT_SECONDS."
        )
    return "Cloud AI is unavailable; check server AI configuration."


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
    provider_error = health.get("provider_error", base.get("provider_error"))

    posture = build_posture_fields(
        deployment_profile=profile,
        reachable=reachable,
        provider=provider,
        litellm_configured=litellm_configured,
        ollama_configured=ollama_configured,
        rules_fallback_enabled=rules_enabled,
        fallback_active=fallback_active,
        provider_error=provider_error,
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
