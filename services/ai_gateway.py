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
from uuid import uuid4

from django.conf import settings
from django.core.cache import cache

from services.ai_schemas import (
    extract_json_from_text,
    validate_dashboard_pack_recommend,
    validate_design_studio,
    validate_doc_classify,
    validate_marketplace_recommend,
    validate_migration_mapping,
    validate_policy_explain,
    validate_report_recommend,
    validate_theme_experience,
    validate_workflow_draft,
)

logger = logging.getLogger(__name__)

# High-confidence prompt-injection / jailbreak phrases — block before provider calls (CI tests cover).
_PROMPT_INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all previous",
    "ignore all prior",
    "disregard your instructions",
    "disregard the above",
    "you are now in developer",
    "jailbreak",
    "override safety",
    "reveal your system prompt",
    "print your instructions",
)


def _looks_like_prompt_injection(*texts: str) -> bool:
    blob = "\n".join(t for t in texts if t).lower()
    return any(m in blob for m in _PROMPT_INJECTION_MARKERS)

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


def _cost_class_for_tier(tier: str | None) -> str:
    tier_name = str(tier or "").strip().lower()
    if tier_name in {"rules", "none"}:
        return "no_cost"
    if tier_name in {"ollama", "vllm"}:
        return "self_hosted"
    if tier_name in {"litellm", "gemini"}:
        return "premium"
    return "unclassified"


def _record_metric(
    date_str: str,
    tenant_id: Any,
    task_type: str,
    tier: str,
    latency_ms: float,
    outcome: str,
    *,
    cost_class: str = "unclassified",
    schema_fail: bool = False,
) -> None:
    """Increment cache bucket for later aggregation into AIGatewayMetric. Tenant-safe."""
    if not getattr(settings, "AI_GATEWAY_METRICS_ENABLED", True):
        return
    key_tenant = str(tenant_id) if tenant_id is not None else "global"
    cache_key = f"ai:metrics:{date_str}:{key_tenant}:{task_type}:{tier}:{cost_class}"
    try:
        raw = cache.get(cache_key)
        bucket = raw if isinstance(raw, dict) else {
            "count": 0,
            "latency_sum": 0.0,
            "failures": 0,
            "schema_fail": 0,
            "review_count": 0,
            "accepted_count": 0,
            "manual_correction_count": 0,
        }
        bucket["count"] = bucket.get("count", 0) + 1
        bucket["latency_sum"] = bucket.get("latency_sum", 0) + latency_ms
        if outcome in ("failure", "fallback"):
            bucket["failures"] = bucket.get("failures", 0) + 1
        if schema_fail:
            bucket["schema_fail"] = bucket.get("schema_fail", 0) + 1
        cache.set(cache_key, bucket, timeout=86400 * 3)
    except Exception as e:
        logger.debug("AI gateway metric record failed: %s", e)


def _record_feedback_metric(
    date_str: str,
    tenant_id: Any,
    task_type: str,
    tier: str,
    *,
    cost_class: str,
    accepted: bool | None = None,
    manual_correction: bool | None = None,
) -> None:
    if not getattr(settings, "AI_GATEWAY_METRICS_ENABLED", True):
        return
    if accepted is None and manual_correction is None:
        return
    key_tenant = str(tenant_id) if tenant_id is not None else "global"
    cache_key = f"ai:metrics:{date_str}:{key_tenant}:{task_type}:{tier}:{cost_class}"
    try:
        raw = cache.get(cache_key)
        bucket = raw if isinstance(raw, dict) else {
            "count": 0,
            "latency_sum": 0.0,
            "failures": 0,
            "schema_fail": 0,
            "review_count": 0,
            "accepted_count": 0,
            "manual_correction_count": 0,
        }
        bucket["review_count"] = bucket.get("review_count", 0) + 1
        if accepted is True:
            bucket["accepted_count"] = bucket.get("accepted_count", 0) + 1
        if manual_correction is True:
            bucket["manual_correction_count"] = bucket.get("manual_correction_count", 0) + 1
        cache.set(cache_key, bucket, timeout=86400 * 3)
    except Exception as e:
        logger.debug("AI gateway feedback metric record failed: %s", e)


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
    cost_class = _cost_class_for_tier(tier)
    payload = {
        "event": "ai_gateway_invoke",
        "task_type": task_type,
        "tier": tier,
        "cost_class": cost_class,
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
            cost_class=cost_class,
            schema_fail=bool(meta and meta.get("schema_validation_failed")),
        )
    except Exception:
        pass
    # Persist to AIActionAuditLog for compliance and audit trail (platform_runtime.helpers.log_ai_action)
    try:
        from apps.platform_runtime.helpers import log_ai_action
        request_id = (meta or {}).get("request_id", "")
        user_id = (meta or {}).get("user_id")
        log_ai_action(
            action_type=f"ai_gateway:{task_type}",
            tenant_id=tenant_id,
            user_id=user_id,
            request_id=request_id,
            payload={
                "tier": tier,
                "model": model,
                "latency_ms": round(latency_ms, 2),
                "outcome": outcome,
                "cost_class": cost_class,
                "school_id": str(school_id) if school_id is not None else None,
            },
        )
    except Exception as e:
        logger.debug("AI action audit log write skipped: %s", e)


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


def _safe_schema_default(response_schema: str | None) -> Any:
    if response_schema == "workflow_draft":
        return {"name": "", "trigger_type": "manual", "steps": [], "description": ""}
    if response_schema == "policy_explain":
        return {"summary": "", "differences": [], "warnings": []}
    if response_schema == "migration_mapping":
        return []
    if response_schema == "doc_classify":
        return {"category": "general", "tags": [], "confidence": 0.0}
    if response_schema == "theme_experience":
        return {"suggestions": [], "rationale": ""}
    if response_schema == "report_recommend":
        return {"recommendations": []}
    if response_schema == "design_studio":
        return {"suggestions": [], "components": []}
    if response_schema == "dashboard_pack_recommend":
        return {"dashboards": [], "packs": [], "rationale": ""}
    if response_schema == "marketplace_recommend":
        return {"recommendations": [], "rationale": ""}
    return None


def _payload_contains_pii(*texts: Any) -> bool:
    try:
        from services.inference import strip_pii_for_inference
    except Exception:
        return False
    for text in texts:
        if not isinstance(text, str):
            continue
        raw = text.strip()
        if not raw:
            continue
        if strip_pii_for_inference(raw) != raw:
            return True
    return False


def _data_tier_allows_premium(metadata: dict[str, Any] | None, *, prompt: str = "", user_query: str = "") -> bool:
    """If payload has PII or tenant disallows external, we must not use premium (litellm/gemini) for sensitive data."""
    if not metadata:
        return not _payload_contains_pii(prompt, user_query)
    if metadata.get("sensitivity_class") == "high" or metadata.get("disallow_external_model"):
        return False
    if _payload_contains_pii(prompt, user_query):
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


def record_feedback(
    task_type: str | TaskType,
    tier: str,
    *,
    tenant_id: Any = None,
    school_id: Any = None,
    accepted: bool | None = None,
    manual_correction: bool | None = None,
    request_date: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    task_key = task_type.value if isinstance(task_type, TaskType) else str(task_type or "").strip().lower()
    if not task_key:
        raise ValueError("task_type is required")
    tier_key = str(tier or "").strip().lower() or "unknown"
    date_str = request_date or date.today().isoformat()
    cost_class = _cost_class_for_tier(tier_key)
    _record_feedback_metric(
        date_str,
        tenant_id or school_id,
        task_key,
        tier_key,
        cost_class=cost_class,
        accepted=accepted,
        manual_correction=manual_correction,
    )
    return {
        "task_type": task_key,
        "tier": tier_key,
        "cost_class": cost_class,
        "tenant_id": str(tenant_id) if tenant_id is not None else (str(school_id) if school_id is not None else None),
        "school_id": str(school_id) if school_id is not None else None,
        "accepted": accepted,
        "manual_correction": manual_correction,
        "request_date": date_str,
        "request_id": request_id,
    }


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
    if _looks_like_prompt_injection(prompt, user_query):
        request_id = str(uuid4())
        request_date = date.today().isoformat()
        out_meta = {
            "provider": "none",
            "prompt_injection_blocked": True,
            "request_id": request_id,
            "request_date": request_date,
            "task_type": task_key,
        }
        logger.warning(
            "ai_gateway: blocked likely prompt injection (task=%s)", task_key
        )
        return None, out_meta
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
    user_id = md.get("user_id")
    request_id = str(uuid4())
    request_date = date.today().isoformat()
    budget_ok, budget_meta = _check_and_consume_budget(tenant_id)
    if not budget_ok:
        out_meta = {
            "provider": "none",
            "budget_exceeded": True,
            "request_id": request_id,
            "request_date": request_date,
            "cost_class": _cost_class_for_tier("none"),
            "user_id": user_id,
            **budget_meta,
        }
        _audit_log(task_key, "none", "", 0, tenant_id, school_id, "budget_exceeded", out_meta)
        return None, out_meta
    allow_premium = _data_tier_allows_premium(md, prompt=prompt, user_query=user_query)
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
            text, meta = _call_vllm(
                prompt,
                metadata=md,
                json_mode=(
                    response_schema in (
                        "workflow_draft",
                        "policy_explain",
                        "migration_mapping",
                        "doc_classify",
                        "theme_experience",
                        "report_recommend",
                        "design_studio",
                        "dashboard_pack_recommend",
                        "marketplace_recommend",
                    )
                ),
                timeout_sec=timeout_sec,
            )
        elif tier == "litellm":
            text, meta = _call_litellm(prompt, metadata=md, timeout_sec=timeout_sec)
        elif tier == "gemini":
            text, meta = _call_gemini(prompt)
        elif tier == "rules":
            elapsed_ms = (time.perf_counter() - start) * 1000
            result = _rules_fallback(user_query or prompt[:200])
            meta = {"fallback": True, "errors": errors} if errors else {"fallback": True}
            meta.update({
                "request_id": request_id,
                "request_date": request_date,
                "task_type": task_key,
                "cost_class": _cost_class_for_tier("rules"),
                "user_id": user_id,
            })
            _audit_log(task_key, "rules", "rules", elapsed_ms, tenant_id, school_id, "success", meta)
            return result, {"provider": "rules", "tier": "rules", "latency_ms": round(elapsed_ms, 2), **meta}
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
                    elif response_schema == "theme_experience" and isinstance(parsed, dict):
                        result = validate_theme_experience(parsed)
                    elif response_schema == "report_recommend" and isinstance(parsed, dict):
                        result = validate_report_recommend(parsed)
                    elif response_schema == "design_studio" and isinstance(parsed, dict):
                        result = validate_design_studio(parsed)
                    elif response_schema == "dashboard_pack_recommend" and isinstance(parsed, dict):
                        result = validate_dashboard_pack_recommend(parsed)
                    elif response_schema == "marketplace_recommend" and isinstance(parsed, dict):
                        result = validate_marketplace_recommend(parsed)
                    else:
                        raise ValueError("invalid_structured_payload")
                except (ValueError, TypeError) as e:
                    logger.warning("Schema validation failed for %s: %s", response_schema, e)
                    schema_validation_failed = True
                    result = _safe_schema_default(response_schema)
            else:
                result = text
            out_meta = {
                **meta,
                "latency_ms": round(elapsed_ms, 2),
                "task_type": task_key,
                "schema_validation_failed": schema_validation_failed,
                "request_id": request_id,
                "request_date": request_date,
                "cost_class": _cost_class_for_tier(tier),
                "user_id": user_id,
            }
            _audit_log(task_key, tier, model, elapsed_ms, tenant_id, school_id, "success", out_meta)
            return result, out_meta
        errors[tier] = meta.get("error", "unavailable")

    elapsed_ms = (time.perf_counter() - start) * 1000
    if bool(getattr(settings, "AI_ALLOW_RULES_FALLBACK", True)):
        result = _rules_fallback(user_query or prompt[:200])
        out_meta = {
            "errors": errors,
            "request_id": request_id,
            "request_date": request_date,
            "cost_class": _cost_class_for_tier("rules"),
            "user_id": user_id,
        }
        _audit_log(task_key, "rules", "rules", elapsed_ms, tenant_id, school_id, "fallback", out_meta)
        return result, {"provider": "rules", "tier": "rules", "latency_ms": round(elapsed_ms, 2), "fallback": True, **out_meta}
    failure_meta = {
        "errors": errors,
        "request_id": request_id,
        "request_date": request_date,
        "cost_class": _cost_class_for_tier("none"),
        "user_id": user_id,
    }
    _audit_log(task_key, "none", "", elapsed_ms, tenant_id, school_id, "failure", failure_meta)
    return (
        "AI providers are currently unavailable and rules fallback is disabled.",
        {"provider": "none", "errors": errors, "latency_ms": round(elapsed_ms, 2), **failure_meta},
    )
