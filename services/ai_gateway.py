"""
RunMyCampus AI Gateway: single entry point for all AI. Task-based routing, tier selection
(Ollama / vLLM / LiteLLM), structured output validation, audit, fallback. No browser calls
providers directly; all traffic goes through this gateway.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import date
from enum import Enum
from typing import Any, TypeVar

from django.conf import settings
from django.core.cache import cache

from services.ai_schemas import (
    extract_json_from_text,
    validate_doc_classify,
    validate_migration_mapping,
    validate_policy_explain,
    validate_workflow_draft,
)

logger = logging.getLogger(__name__)

# Task types (align with blueprint)
class TaskType(str, Enum):
    CONFIG_EXPLAIN = "config_explain"
    SETUP_RECOMMEND = "setup_recommend"
    WORKFLOW_DRAFT = "workflow_draft"
    POLICY_EXPLAIN = "policy_explain"
    DOC_CLASSIFY = "doc_classify"
    SEMANTIC_SEARCH = "semantic_search"
    MIGRATION_MAPPING = "migration_mapping"
    MIGRATION_FINGERPRINT = "migration_fingerprint"
    MIGRATION_PARITY = "migration_parity"
    ADMIN_COPILOT = "admin_copilot"
    SUPPORT_SUGGEST = "support_suggest"
    NARRATIVE = "narrative"
    GENERAL_CHAT = "general_chat"


# Default tier per task (Class A/B/C/D). Override via AI_GATEWAY_TASK_TIERS.
DEFAULT_TASK_TIERS: dict[str, list[str]] = {
    TaskType.CONFIG_EXPLAIN: ["ollama", "vllm", "rules"],
    TaskType.SETUP_RECOMMEND: ["ollama", "vllm", "rules"],
    TaskType.WORKFLOW_DRAFT: ["vllm", "ollama", "rules"],
    TaskType.POLICY_EXPLAIN: ["vllm", "ollama", "rules"],
    TaskType.DOC_CLASSIFY: ["ollama", "vllm", "rules"],
    TaskType.SEMANTIC_SEARCH: ["ollama", "rules"],
    TaskType.MIGRATION_MAPPING: ["vllm", "litellm", "ollama", "rules"],
    TaskType.MIGRATION_FINGERPRINT: ["vllm", "ollama", "rules"],
    TaskType.MIGRATION_PARITY: ["vllm", "ollama", "rules"],
    TaskType.ADMIN_COPILOT: ["ollama", "vllm", "rules"],
    TaskType.SUPPORT_SUGGEST: ["ollama", "vllm", "rules"],
    TaskType.NARRATIVE: ["ollama", "rules"],
    TaskType.GENERAL_CHAT: ["ollama", "gemini", "rules"],
}


def _task_tiers() -> dict[str, list[str]]:
    custom = getattr(settings, "AI_GATEWAY_TASK_TIERS", None) or os.environ.get("AI_GATEWAY_TASK_TIERS")
    if custom and isinstance(custom, dict):
        out = dict(DEFAULT_TASK_TIERS)
        for k, v in custom.items():
            if isinstance(v, list):
                out[k] = [str(x).lower() for x in v]
            elif isinstance(v, str):
                out[k] = [x.strip().lower() for x in v.split(",") if x.strip()]
        return out
    return {k.value: v for k, v in DEFAULT_TASK_TIERS.items()}


def _request_timeout(metadata: dict[str, Any] | None = None) -> int:
    base = 25
    raw = getattr(settings, "AI_PROVIDER_TIMEOUT_SECONDS", None) or os.environ.get("AI_PROVIDER_TIMEOUT_SECONDS") or "25"
    try:
        base = max(5, min(int(raw), 90))
    except (TypeError, ValueError):
        pass
    if metadata:
        lt = metadata.get("latency_target")
        if lt is not None:
            try:
                cap = max(5, min(int(lt), 90))
                return min(base, cap)
            except (TypeError, ValueError):
                pass
    return base


def _record_metric(
    date_str: str,
    tenant_id: Any,
    task_type: str,
    tier: str,
    latency_ms: float,
    outcome: str,
    schema_fail: bool = False,
) -> None:
    """Increment cache bucket for later aggregation into AIGatewayMetric. Tenant-safe."""
    if not getattr(settings, "AI_GATEWAY_METRICS_ENABLED", True):
        return
    key_tenant = str(tenant_id) if tenant_id is not None else "global"
    cache_key = f"ai:metrics:{date_str}:{key_tenant}:{task_type}:{tier}"
    try:
        raw = cache.get(cache_key)
        bucket = raw if isinstance(raw, dict) else {"count": 0, "latency_sum": 0.0, "failures": 0, "schema_fail": 0}
        bucket["count"] = bucket.get("count", 0) + 1
        bucket["latency_sum"] = bucket.get("latency_sum", 0) + latency_ms
        if outcome in ("failure", "fallback"):
            bucket["failures"] = bucket.get("failures", 0) + 1
        if schema_fail:
            bucket["schema_fail"] = bucket.get("schema_fail", 0) + 1
        cache.set(cache_key, bucket, timeout=86400 * 3)
    except Exception as e:
        logger.debug("AI gateway metric record failed: %s", e)


def _audit_log(
    task_type: str,
    tier: str,
    model: str,
    latency_ms: float,
    tenant_id: Any,
    school_id: Any,
    outcome: str,
    meta: dict[str, Any] | None = None,
) -> None:
    payload = {
        "event": "ai_gateway_invoke",
        "task_type": task_type,
        "tier": tier,
        "model": model,
        "latency_ms": round(latency_ms, 2),
        "tenant_id": str(tenant_id) if tenant_id is not None else None,
        "school_id": str(school_id) if school_id is not None else None,
        "outcome": outcome,
        **(meta or {}),
    }
    # Tenant-safe: do not log prompt/response content
    logger.info("AI gateway audit: %s", json.dumps({k: v for k, v in payload.items() if v is not None}))
    try:
        _record_metric(
            date.today().isoformat(),
            tenant_id,
            task_type,
            tier,
            latency_ms,
            outcome,
            schema_fail=bool(meta and meta.get("schema_validation_failed")),
        )
    except Exception:
        pass


def _call_ollama(prompt: str, metadata: dict[str, Any] | None = None) -> tuple[str | None, dict[str, Any]]:
    from apps.portal.ai_provider import _call_ollama as _ollama
    text = _ollama(prompt, metadata=metadata)
    return text, {"provider": "ollama", "tier": "ollama"}


def _call_vllm(prompt: str, metadata: dict[str, Any] | None = None, json_mode: bool = False, timeout_sec: int | None = None) -> tuple[str | None, dict[str, Any]]:
    endpoint = (getattr(settings, "VLLM_ENDPOINT", None) or os.environ.get("VLLM_ENDPOINT") or "").strip().rstrip("/")
    if not endpoint:
        return None, {"provider": "vllm", "error": "VLLM_ENDPOINT not set"}
    model = (getattr(settings, "VLLM_MODEL", None) or os.environ.get("VLLM_MODEL") or "default").strip()
    url = f"{endpoint}/v1/completions" if "/v1" not in endpoint else f"{endpoint.rstrip('/')}/completions"
    if not url.startswith("http"):
        url = f"http://{url}"
    payload = {
        "model": model,
        "prompt": prompt,
        "max_tokens": 2048,
        "temperature": 0.3,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    timeout = timeout_sec if timeout_sec is not None else _request_timeout(metadata)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        choices = body.get("choices") or []
        text = (choices[0].get("text") or "").strip() if choices else None
        return text or None, {"provider": "vllm", "tier": "vllm", "model": model}
    except urllib.error.HTTPError as e:
        logger.warning("vLLM HTTP error %s: %s", e.code, url)
        return None, {"provider": "vllm", "error": f"http_{e.code}"}
    except urllib.error.URLError as e:
        logger.debug("vLLM request failed: %s", e.reason)
        return None, {"provider": "vllm", "error": "unavailable"}
    except Exception as e:
        logger.exception("vLLM call failed")
        return None, {"provider": "vllm", "error": str(e)[:200]}


def _call_litellm(prompt: str, metadata: dict[str, Any] | None = None, model_key: str | None = None, timeout_sec: int | None = None) -> tuple[str | None, dict[str, Any]]:
    proxy_url = (getattr(settings, "LITELLM_PROXY_URL", None) or os.environ.get("LITELLM_PROXY_URL") or "").strip().rstrip("/")
    if not proxy_url:
        return None, {"provider": "litellm", "error": "LITELLM_PROXY_URL not set"}
    model = (model_key or getattr(settings, "LITELLM_MODEL", None) or os.environ.get("LITELLM_MODEL") or "gpt-3.5-turbo").strip()
    url = f"{proxy_url}/v1/chat/completions" if "/v1/" not in proxy_url else f"{proxy_url}/chat/completions"
    if not url.startswith("http"):
        url = f"https://{url}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2048,
        "temperature": 0.3,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    timeout = timeout_sec if timeout_sec is not None else _request_timeout(metadata)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        choices = body.get("choices") or []
        msg = choices[0].get("message", {}) if choices else {}
        text = (msg.get("content") or "").strip()
        return text or None, {"provider": "litellm", "tier": "litellm", "model": model}
    except urllib.error.HTTPError as e:
        logger.warning("LiteLLM HTTP error %s: %s", e.code, url)
        return None, {"provider": "litellm", "error": f"http_{e.code}"}
    except urllib.error.URLError as e:
        logger.debug("LiteLLM request failed: %s", getattr(e, "reason", e))
        return None, {"provider": "litellm", "error": "unavailable"}
    except Exception as e:
        logger.exception("LiteLLM call failed")
        return None, {"provider": "litellm", "error": str(e)[:200]}


def _call_gemini(prompt: str) -> tuple[str | None, dict[str, Any]]:
    from apps.portal.ai_provider import _call_gemini as _gemini
    text = _gemini(prompt)
    return text, {"provider": "gemini", "tier": "gemini"} if text else (None, {"provider": "gemini", "error": "unavailable"})


def _rules_fallback(user_query: str) -> str:
    from apps.portal.ai_provider import _rules_fallback as _rules
    return _rules(user_query)


def _data_tier_allows_premium(metadata: dict[str, Any] | None) -> bool:
    """If payload has PII or tenant disallows external, we must not use premium (litellm/gemini) for sensitive data."""
    if not metadata:
        return True
    if metadata.get("sensitivity_class") == "high" or metadata.get("disallow_external_model"):
        return False
    return True


def _budget_limit_per_tenant_per_day() -> int:
    """0 = disabled. Otherwise max requests per tenant per calendar day."""
    raw = getattr(settings, "AI_GATEWAY_BUDGET_REQUESTS_PER_TENANT_DAY", None) or os.environ.get("AI_GATEWAY_BUDGET_REQUESTS_PER_TENANT_DAY") or "0"
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def _check_and_consume_budget(tenant_id: Any) -> tuple[bool, dict[str, Any]]:
    """
    Check per-tenant daily request budget; if under limit, increment and return (True, {}).
    Otherwise return (False, {budget_exceeded: True, ...}). When limit is 0, budget is disabled.
    """
    limit = _budget_limit_per_tenant_per_day()
    if limit <= 0:
        return True, {}
    key_tenant = str(tenant_id) if tenant_id is not None else "global"
    today = date.today().isoformat()
    cache_key = f"ai:budget:requests:{key_tenant}:{today}"
    # Race: get and incr; we allow slightly over limit under contention
    try:
        current = cache.get(cache_key, 0) or 0
        if current >= limit:
            return False, {"budget_exceeded": True, "limit": limit, "period": "day"}
        if current == 0:
            cache.set(cache_key, 1, timeout=86400 * 2)  # 2 days TTL to cover day boundary
        else:
            cache.incr(cache_key)
    except Exception:
        # If cache fails, allow the request (fail open)
        return True, {}
    return True, {}


T = TypeVar("T")


def invoke(
    task_type: str | TaskType,
    prompt: str,
    *,
    user_query: str = "",
    metadata: dict[str, Any] | None = None,
    response_schema: str | None = None,
) -> tuple[Any, dict[str, Any]]:
    """
    Single gateway entry. Returns (result, meta). result is str or validated structured object
    when response_schema is set (workflow_draft, policy_explain, migration_mapping, doc_classify).

    Request metadata (optional, in metadata dict): sensitivity_class, latency_target (seconds),
    output_type, allowed_backends (list of tier names). See docs/architecture/ai_orchestration.md.
    """
    task = TaskType(task_type) if isinstance(task_type, str) else task_type
    task_key = task.value
    tiers_map = _task_tiers()
    backends = tiers_map.get(task_key, ["ollama", "rules"])
    md = metadata or {}
    allowed = md.get("allowed_backends")
    if allowed is not None and isinstance(allowed, (list, tuple)):
        allowed_set = {str(t).lower() for t in allowed}
        backends = [t for t in backends if t in allowed_set]
        if not backends:
            backends = tiers_map.get(task_key, ["ollama", "rules"])
    tenant_id = md.get("tenant_id") or md.get("school_id")
    school_id = md.get("school_id")
    budget_ok, budget_meta = _check_and_consume_budget(tenant_id)
    if not budget_ok:
        _audit_log(task_key, "none", "", 0, tenant_id, school_id, "budget_exceeded", budget_meta)
        return None, {"provider": "none", "budget_exceeded": True, **budget_meta}
    allow_premium = _data_tier_allows_premium(md)
    timeout_sec = _request_timeout(md)
    errors: dict[str, str] = {}
    start = time.perf_counter()

    for tier in backends:
        if tier == "litellm" or tier == "gemini":
            if not allow_premium:
                errors[tier] = "data_tier_disallowed"
                continue
        text = None
        meta: dict[str, Any] = {}
        if tier == "ollama":
            text, meta = _call_ollama(prompt, metadata=md)
        elif tier == "vllm":
            text, meta = _call_vllm(prompt, metadata=md, json_mode=(response_schema in ("workflow_draft", "policy_explain", "migration_mapping", "doc_classify")), timeout_sec=timeout_sec)
        elif tier == "litellm":
            text, meta = _call_litellm(prompt, metadata=md, timeout_sec=timeout_sec)
        elif tier == "gemini":
            text, meta = _call_gemini(prompt)
        elif tier == "rules":
            elapsed_ms = (time.perf_counter() - start) * 1000
            result = _rules_fallback(user_query or prompt[:200])
            _audit_log(task_key, "rules", "rules", elapsed_ms, tenant_id, school_id, "success", {"fallback": True})
            return result, {"provider": "rules", "tier": "rules", "latency_ms": round(elapsed_ms, 2), "fallback": True}
        if text:
            elapsed_ms = (time.perf_counter() - start) * 1000
            model = meta.get("model", tier)
            schema_validation_failed = False
            if response_schema:
                parsed = extract_json_from_text(text)
                try:
                    if response_schema == "workflow_draft" and isinstance(parsed, dict):
                        result = validate_workflow_draft(parsed)
                    elif response_schema == "policy_explain" and isinstance(parsed, dict):
                        result = validate_policy_explain(parsed)
                    elif response_schema == "migration_mapping":
                        result = validate_migration_mapping(parsed if parsed is not None else [])
                    elif response_schema == "doc_classify" and isinstance(parsed, dict):
                        result = validate_doc_classify(parsed)
                    else:
                        result = text
                except (ValueError, TypeError) as e:
                    logger.warning("Schema validation failed for %s: %s", response_schema, e)
                    schema_validation_failed = True
                    result = text
            else:
                result = text
            out_meta = {**meta, "latency_ms": round(elapsed_ms, 2), "task_type": task_key, "schema_validation_failed": schema_validation_failed}
            _audit_log(task_key, tier, model, elapsed_ms, tenant_id, school_id, "success", out_meta)
            return result, out_meta
        errors[tier] = meta.get("error", "unavailable")

    elapsed_ms = (time.perf_counter() - start) * 1000
    if bool(getattr(settings, "AI_ALLOW_RULES_FALLBACK", True)):
        result = _rules_fallback(user_query or prompt[:200])
        _audit_log(task_key, "rules", "rules", elapsed_ms, tenant_id, school_id, "fallback", {"errors": errors})
        return result, {"provider": "rules", "tier": "rules", "latency_ms": round(elapsed_ms, 2), "fallback": True, "errors": errors}
    _audit_log(task_key, "none", "", elapsed_ms, tenant_id, school_id, "failure", {"errors": errors})
    return (
        "AI providers are currently unavailable and rules fallback is disabled.",
        {"provider": "none", "errors": errors, "latency_ms": round(elapsed_ms, 2)},
    )
