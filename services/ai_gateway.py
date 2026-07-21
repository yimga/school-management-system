"""
RunMyCampus AI Gateway: single entry point for all AI. Task-based routing, tier selection
(Ollama / vLLM / LiteLLM / rules), structured output validation, audit, fallback.
General in-product chat uses Ollama + rules only (no Google Gemini or other cloud LLM in
that path). No browser calls providers directly; all traffic goes through this gateway.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import date
from enum import Enum
from typing import Any, TypeVar
from uuid import uuid4

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError

from services.ai_deployment_posture import litellm_api_key, litellm_model, litellm_proxy_url

# Typed handlers for non-fatal side effects (metrics, cache, audit persistence).
_CACHE_METRIC_ERRORS = (
    TypeError,
    ValueError,
    OSError,
    RuntimeError,
    ConnectionError,
    EOFError,
    TimeoutError,
)
_AI_AUDIT_PERSIST_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    KeyError,
    DatabaseError,
)
_AI_PROVIDER_CALL_ERRORS = (
    TimeoutError,
    OSError,
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
)
_AI_GATEWAY_RUNTIME_ERRORS = (
    DatabaseError,
    TimeoutError,
    OSError,
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)

from services.ai_schemas import (
    extract_json_from_text,
    validate_dashboard_pack_recommend,
    validate_design_studio,
    validate_doc_classify,
    validate_guided_assistant,
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
    # Domain guided assistants (structured JSON; same tier policy as admin_copilot)
    INTEROP_ASSISTANT = "interop_assistant"
    RUNTIME_CONFIG_EXPLAIN = "runtime_config_explain"
    OBSERVABILITY_ASSISTANT = "observability_assistant"
    BILLING_USAGE_EXPLAIN = "billing_usage_explain"
    TRUST_COMPLIANCE_ASSISTANT = "trust_compliance_assistant"
    STUDIO_OS_ASSISTANT = "studio_os_assistant"
    # Pass 13: explain why a student was flagged at-risk.
    RISK_EXPLAIN = "risk_explain"
    # Pass 13.B: draft a parent-facing message from a short brief. Always
    # produced as a draft — humans approve before sending.
    TEACHER_COMMS_DRAFT = "teacher_comms_draft"
    # Pass 13.B: report-card narrative comment for one student × one term.
    REPORT_CARD_COMMENT = "report_card_comment"


# Default tier per task follows RMC_DEPLOYMENT_PROFILE (services.ai_deployment_posture).
# online + LITELLM_PROXY_URL → litellm, ollama, rules; edge → ollama, rules.
# Optional per-task override: Django settings.AI_GATEWAY_TASK_TIERS dict.
_DEFAULT_OLLAMA_RULES: list[str] = ["ollama", "rules"]

DEFAULT_TASK_TIERS: dict[str, list[str]] = {
    TaskType.CONFIG_EXPLAIN: list(_DEFAULT_OLLAMA_RULES),
    TaskType.SETUP_RECOMMEND: list(_DEFAULT_OLLAMA_RULES),
    TaskType.WORKFLOW_DRAFT: list(_DEFAULT_OLLAMA_RULES),
    TaskType.POLICY_EXPLAIN: list(_DEFAULT_OLLAMA_RULES),
    TaskType.DOC_CLASSIFY: list(_DEFAULT_OLLAMA_RULES),
    TaskType.SEMANTIC_SEARCH: list(_DEFAULT_OLLAMA_RULES),
    TaskType.MIGRATION_MAPPING: list(_DEFAULT_OLLAMA_RULES),
    TaskType.MIGRATION_FINGERPRINT: list(_DEFAULT_OLLAMA_RULES),
    TaskType.MIGRATION_PARITY: list(_DEFAULT_OLLAMA_RULES),
    TaskType.ADMIN_COPILOT: list(_DEFAULT_OLLAMA_RULES),
    TaskType.SUPPORT_SUGGEST: list(_DEFAULT_OLLAMA_RULES),
    TaskType.NARRATIVE: list(_DEFAULT_OLLAMA_RULES),
    TaskType.GENERAL_CHAT: list(_DEFAULT_OLLAMA_RULES),
    TaskType.INTEROP_ASSISTANT: list(_DEFAULT_OLLAMA_RULES),
    TaskType.RUNTIME_CONFIG_EXPLAIN: list(_DEFAULT_OLLAMA_RULES),
    TaskType.OBSERVABILITY_ASSISTANT: list(_DEFAULT_OLLAMA_RULES),
    TaskType.BILLING_USAGE_EXPLAIN: list(_DEFAULT_OLLAMA_RULES),
    TaskType.TRUST_COMPLIANCE_ASSISTANT: list(_DEFAULT_OLLAMA_RULES),
    TaskType.STUDIO_OS_ASSISTANT: list(_DEFAULT_OLLAMA_RULES),
    TaskType.RISK_EXPLAIN: list(_DEFAULT_OLLAMA_RULES),
    # Pass 13.B: teacher comms drafts and report-card comments — same tier
    # policy as risk_explain (premium-first, on-prem fallback, rules as last resort).
    TaskType.TEACHER_COMMS_DRAFT: list(_DEFAULT_OLLAMA_RULES),
    TaskType.REPORT_CARD_COMMENT: list(_DEFAULT_OLLAMA_RULES),
}


def _task_tiers() -> dict[str, list[str]]:
    from services.ai_deployment_posture import merge_effective_task_tiers

    custom = getattr(settings, "AI_GATEWAY_TASK_TIERS", None)
    if custom and isinstance(custom, dict):
        return merge_effective_task_tiers(custom)
    return merge_effective_task_tiers(None)


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


# ---------------------------------------------------------------------------
# Per-tier circuit breaker (in-process; no DB / migration).
#
# When a network tier (litellm / vllm / removed_cloud_provider) keeps failing
# — e.g. an upstream that hangs to the full request timeout — every invoke()
# would otherwise re-probe it and burn the timeout again, starving worker
# threads under load (the same failure mode behind the SSE thread-starvation
# incident). After N consecutive call failures the tier's circuit OPENS for a
# cooldown window: subsequent calls skip that tier immediately (fast-failover
# to the next tier / rules), and the first probe after the window half-opens to
# re-test. The deterministic "rules" tier is never circuit-broken so graceful
# degradation always remains available.
#
# Env escape hatch (secure/resilient by default, fully tunable):
#   AI_GATEWAY_CIRCUIT_BREAKER_ENABLED   default "1"  ("0" disables entirely)
#   AI_GATEWAY_CIRCUIT_FAIL_THRESHOLD    default 3    consecutive failures to open
#   AI_GATEWAY_CIRCUIT_COOLDOWN_SECONDS  default 30   open-state skip window
# ---------------------------------------------------------------------------
_CIRCUIT_STATE: dict[str, dict[str, float]] = {}
_CIRCUIT_LOCK = threading.Lock()
# Tiers that make a real outbound network call and can hang on a bad upstream.
# Local/cheap tiers and the deterministic fallback are intentionally excluded.
_CIRCUIT_BREAKABLE_TIERS = frozenset({"litellm", "vllm", "removed_cloud_provider", "ollama"})


def _circuit_enabled() -> bool:
    raw = (os.environ.get("AI_GATEWAY_CIRCUIT_BREAKER_ENABLED") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _circuit_fail_threshold() -> int:
    try:
        return max(1, int(os.environ.get("AI_GATEWAY_CIRCUIT_FAIL_THRESHOLD") or "3"))
    except (TypeError, ValueError):
        return 3


def _circuit_cooldown_seconds() -> float:
    try:
        return max(1.0, float(os.environ.get("AI_GATEWAY_CIRCUIT_COOLDOWN_SECONDS") or "30"))
    except (TypeError, ValueError):
        return 30.0


def _circuit_is_open(tier: str) -> bool:
    """True iff this tier should be skipped right now (open circuit, still cooling)."""
    if not _circuit_enabled() or tier not in _CIRCUIT_BREAKABLE_TIERS:
        return False
    with _CIRCUIT_LOCK:
        st = _CIRCUIT_STATE.get(tier)
        if not st:
            return False
        return st.get("opened_until", 0.0) > time.monotonic()


def _circuit_record_failure(tier: str) -> None:
    if not _circuit_enabled() or tier not in _CIRCUIT_BREAKABLE_TIERS:
        return
    threshold = _circuit_fail_threshold()
    with _CIRCUIT_LOCK:
        st = _CIRCUIT_STATE.setdefault(tier, {"failures": 0.0, "opened_until": 0.0})
        st["failures"] = st.get("failures", 0.0) + 1
        if st["failures"] >= threshold:
            st["opened_until"] = time.monotonic() + _circuit_cooldown_seconds()
            logger.warning(
                "ai_gateway circuit OPEN for tier=%s after %d consecutive failures; "
                "skipping for %.0fs",
                tier, int(st["failures"]), _circuit_cooldown_seconds(),
            )


def _circuit_record_success(tier: str) -> None:
    if tier not in _CIRCUIT_BREAKABLE_TIERS:
        return
    with _CIRCUIT_LOCK:
        if tier in _CIRCUIT_STATE:
            _CIRCUIT_STATE[tier] = {"failures": 0.0, "opened_until": 0.0}


def reset_ai_gateway_circuits() -> None:
    """Test/operational hook — clear all circuit-breaker state."""
    with _CIRCUIT_LOCK:
        _CIRCUIT_STATE.clear()


def _cost_class_for_tier(tier: str | None) -> str:
    tier_name = str(tier or "").strip().lower()
    if tier_name in {"rules", "none"}:
        return "no_cost"
    if tier_name in {"ollama", "vllm"}:
        return "self_hosted"
    if tier_name == "litellm":
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
    except _CACHE_METRIC_ERRORS as e:
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
    except _CACHE_METRIC_ERRORS as e:
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
    except _CACHE_METRIC_ERRORS:
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
    except _AI_AUDIT_PERSIST_ERRORS as e:
        logger.debug("AI action audit log write skipped: %s", e)


def _call_ollama(prompt: str, metadata: dict[str, Any] | None = None) -> tuple[str | None, dict[str, Any]]:
    from services.ollama_runtime import ensure_ollama_reachable

    ensure_ollama_reachable()
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
            raw = resp.read().decode("utf-8")
        body = json.loads(raw)
        choices = body.get("choices") or []
        text = (choices[0].get("text") or "").strip() if choices else None
        return text or None, {"provider": "vllm", "tier": "vllm", "model": model}
    except urllib.error.HTTPError as e:
        logger.warning("vLLM HTTP error %s: %s", e.code, url)
        return None, {"provider": "vllm", "error": f"http_{e.code}"}
    except urllib.error.URLError as e:
        logger.debug("vLLM request failed: %s", e.reason)
        return None, {"provider": "vllm", "error": "unavailable"}
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.warning("vLLM response parse failed: %s", e)
        return None, {"provider": "vllm", "error": "invalid_response"}
    except TimeoutError:
        return None, {"provider": "vllm", "error": "timeout"}


def _call_litellm(prompt: str, metadata: dict[str, Any] | None = None, model_key: str | None = None, timeout_sec: int | None = None) -> tuple[str | None, dict[str, Any]]:
    proxy_url = litellm_proxy_url()
    if not proxy_url:
        return None, {"provider": "litellm", "error": "LITELLM_PROXY_URL not set"}
    model = litellm_model(model_key=model_key)
    url = f"{proxy_url}/v1/chat/completions" if "/v1/" not in proxy_url else f"{proxy_url}/chat/completions"
    if not url.startswith("http"):
        url = f"https://{url}"
    headers = {"Content-Type": "application/json"}
    api_key = litellm_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    timeout = timeout_sec if timeout_sec is not None else _request_timeout(metadata)
    # LiteLLM is a third-party processor: the bytes that leave this process must
    # be the REDACTED text, never the original. Redaction here (not at the call
    # site) means no caller can route around it. If it cannot run, we do not call.
    outbound_prompt = _redact_for_external_transport(prompt, metadata)
    if outbound_prompt is None:
        return None, {"provider": "litellm", "error": "redaction_unavailable"}
    base_messages = [{"role": "user", "content": outbound_prompt}]

    def _post(extra: dict[str, Any]) -> tuple[str | None, dict[str, Any], int | None]:
        """One completion attempt. Third element is the HTTP status (None for
        non-HTTP failures so the caller knows a param-retry cannot help)."""
        payload = {"model": model, "messages": base_messages, **extra}
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
            body = json.loads(raw)
            choices = body.get("choices") or []
            msg = choices[0].get("message", {}) if choices else {}
            text = (msg.get("content") or "").strip()
            return text or None, {"provider": "litellm", "tier": "litellm", "model": model}, None
        except urllib.error.HTTPError as e:
            return None, {"provider": "litellm", "error": f"http_{e.code}"}, e.code
        except urllib.error.URLError as e:
            logger.debug("LiteLLM request failed: %s", getattr(e, "reason", e))
            return None, {"provider": "litellm", "error": "unavailable"}, None
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning("LiteLLM response parse failed: %s", e)
            return None, {"provider": "litellm", "error": "invalid_response"}, None
        except TimeoutError:
            return None, {"provider": "litellm", "error": "timeout"}, None

    # Parameter-shape fallback chain. A model your key supports can still 400 on
    # param rules: reasoning models (gpt-5 / o-series) reject a non-default
    # temperature; legacy models want max_tokens not max_completion_tokens. Only a
    # 400 triggers the next shape — 401/404/429/5xx and non-HTTP errors return as-is
    # (retrying params would not help and would just add latency).
    attempts = (
        {"max_completion_tokens": 2048, "temperature": 0.3},
        {"max_completion_tokens": 2048},  # drop temperature (reasoning models)
        {"max_tokens": 2048},             # legacy token-param name
    )
    text, meta, code = None, {"provider": "litellm", "error": "unavailable"}, None
    for extra in attempts:
        text, meta, code = _post(extra)
        if text is not None or code is None:
            return text, meta
        if code != 400:
            logger.warning("LiteLLM HTTP error %s: %s", code, url)
            return text, meta
    logger.warning("LiteLLM HTTP 400 after parameter-adaptation retries: %s", url)
    return text, meta


def _call_removed_cloud_provider(
    prompt: str,
    metadata: dict[str, Any] | None = None,
    model_key: str | None = None,
    timeout_sec: int | None = None,
) -> tuple[str | None, dict[str, Any]]:
    return None, {"provider": "removed_cloud_provider", "error": "disabled"}


def _rules_fallback(user_query: str) -> str:
    from apps.portal.ai_provider import _rules_fallback as _rules
    return _rules(user_query)


def _live_provider_configured() -> bool:
    try:
        from apps.portal.ai_provider import get_ai_provider_status
        from services.ai_deployment_posture import is_litellm_configured

        status = get_ai_provider_status()
        return is_litellm_configured() or bool(status.get("ollama_configured"))
    except (ImportError, AttributeError, TypeError, ValueError):
        return False


def _live_provider_reachable() -> bool:
    try:
        from apps.portal.ai_provider import probe_ai_provider_reachable

        return bool(probe_ai_provider_reachable().get("reachable"))
    except (ImportError, AttributeError, TypeError, ValueError, OSError):
        return False


def _rules_invoke_result(
    task_key: str,
    user_query: str,
    prompt: str,
    response_schema: str | None,
    metadata: dict[str, Any] | None,
) -> Any:
    """Rules-tier payload: structured dict for guided_assistant, else legacy string or schema default."""
    if response_schema == "guided_assistant":
        from services.ai_guided_fallback import build_guided_fallback

        rag = (metadata or {}).get("rag_snippets")
        snippets = rag if isinstance(rag, list) else None
        return build_guided_fallback(
            task_type=task_key,
            user_query=user_query or "",
            rag_snippets=snippets,
            live_provider_available=_live_provider_reachable(),
            metadata=metadata,
        )
    if response_schema:
        default = _safe_schema_default(response_schema)
        if default is not None:
            return default
    return _rules_fallback(user_query or prompt[:200])


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
    if response_schema == "guided_assistant":
        return {
            "summary": "",
            "actions": [],
            "cautions": [],
            "references": [],
        }
    return None


def _payload_contains_pii(*texts: Any) -> bool:
    """Fail CLOSED: when the detector cannot run, assume the payload is personal data.

    A detector that is unavailable must never be read as "no PII" — that turns
    an import error into permission to post a student record to a third-party
    processor.
    """
    try:
        from services.inference import contains_hard_pii
    except ImportError:
        logger.warning(
            "ai_gateway: PII detector unavailable; treating payload as PII (fail closed)"
        )
        return True
    for text in texts:
        if not isinstance(text, str):
            continue
        raw = text.strip()
        if not raw:
            continue
        try:
            if contains_hard_pii(raw):
                return True
        except _AI_GATEWAY_RUNTIME_ERRORS as exc:
            logger.warning(
                "ai_gateway: PII detection failed (%s); treating payload as PII", exc
            )
            return True
    return False


# Sensitivity classes a caller may declare to permit external (premium)
# processing. Anything else — including an absent or unrecognised class — is
# UNKNOWN and denies. Overridable per deployment (settings or env, comma list).
_DEFAULT_EXTERNAL_SENSITIVITY_ALLOWLIST: tuple[str, ...] = (
    "low",
    "medium",
    "public",
    "internal",
)


def _external_sensitivity_allowlist() -> frozenset[str]:
    raw = (
        getattr(settings, "AI_EXTERNAL_ALLOWED_SENSITIVITY_CLASSES", None)
        or os.environ.get("AI_EXTERNAL_ALLOWED_SENSITIVITY_CLASSES")
        or ""
    )
    if isinstance(raw, str):
        items = [p.strip().lower() for p in raw.split(",") if p.strip()]
    elif isinstance(raw, (list, tuple, set, frozenset)):
        items = [str(p).strip().lower() for p in raw if str(p).strip()]
    else:
        items = []
    return frozenset(items or _DEFAULT_EXTERNAL_SENSITIVITY_ALLOWLIST)


def _data_tier_allows_premium(metadata: dict[str, Any] | None, *, prompt: str = "", user_query: str = "") -> bool:
    """Whether this payload may be sent to the external premium tier (litellm).

    Deny-by-default. Premium is permitted only when ALL hold:
      * the tenant/caller has not set ``disallow_external_model``;
      * the caller explicitly declared a ``sensitivity_class`` on the allowlist
        — an absent or unrecognised class is UNKNOWN and denies;
      * no hard personal identifier is detectable in the payload text.
    """
    md = metadata or {}
    if md.get("disallow_external_model"):
        return False
    declared = md.get("sensitivity_class")
    declared_key = str(declared).strip().lower() if declared is not None else ""
    # Explicit deny kept visible even though the allowlist already excludes it.
    if declared_key == "high":
        return False
    if declared_key not in _external_sensitivity_allowlist():
        return False
    if _payload_contains_pii(prompt, user_query):
        return False
    return True


def _redact_for_external_transport(text: str, metadata: dict[str, Any] | None) -> str | None:
    """Redact a payload that is about to leave the platform.

    Returns ``None`` when redaction cannot be performed; the caller must then
    NOT make the outbound call (fail closed).
    """
    try:
        from services.inference import redact_for_external_inference
    except ImportError:
        logger.warning(
            "ai_gateway: redactor unavailable; refusing external call (fail closed)"
        )
        return None
    try:
        return redact_for_external_inference(text, metadata)
    except _AI_GATEWAY_RUNTIME_ERRORS as exc:
        logger.warning(
            "ai_gateway: outbound redaction failed (%s); refusing external call", exc
        )
        return None


def _budget_limit_per_tenant_per_day() -> int:
    """0 = disabled. Otherwise max requests per tenant per calendar day."""
    raw = getattr(settings, "AI_GATEWAY_BUDGET_REQUESTS_PER_TENANT_DAY", None) or os.environ.get("AI_GATEWAY_BUDGET_REQUESTS_PER_TENANT_DAY") or "0"
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def _premium_budget_limit_per_tenant_per_day(tenant_id: Any) -> int:
    """
    Pass 13.C: per-tenant cap on premium-tier calls per
    day. Resolution order:
      1. school.settings["ai_premium_daily_cap"] — tenant-self-managed.
      2. settings.AI_PREMIUM_DAILY_CAP_PER_TENANT — platform default.
      3. env AI_PREMIUM_DAILY_CAP_PER_TENANT.
      0 / unset → disabled.
    """
    try:
        from apps.schools.models import School

        if tenant_id:
            school = School.objects.filter(id=tenant_id).only("settings").first()
            tenant_settings = getattr(school, "settings", None) or {}
            override = tenant_settings.get("ai_premium_daily_cap")
            if override is not None:
                try:
                    parsed = int(override)
                    if parsed >= 0:
                        return parsed
                except (TypeError, ValueError):
                    pass
    except (ImportError, DatabaseError, AttributeError, TypeError, ValueError):
        pass
    raw = (
        getattr(settings, "AI_PREMIUM_DAILY_CAP_PER_TENANT", None)
        or os.environ.get("AI_PREMIUM_DAILY_CAP_PER_TENANT")
        or "0"
    )
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def _check_and_consume_premium_budget(tenant_id: Any) -> tuple[bool, dict[str, Any]]:
    """Pass 13.C: gate premium-tier providers separately from request budget."""
    limit = _premium_budget_limit_per_tenant_per_day(tenant_id)
    if limit <= 0:
        return True, {}
    key_tenant = str(tenant_id) if tenant_id is not None else "global"
    today = date.today().isoformat()
    cache_key = f"ai:premium_budget:requests:{key_tenant}:{today}"
    try:
        current = cache.get(cache_key, 0) or 0
        if current >= limit:
            return False, {
                "premium_budget_exceeded": True,
                "limit": limit,
                "period": "day",
            }
        # Atomically seed the day-bucket then increment. ``cache.add`` is a
        # no-op when the key already exists, so two concurrent cold-start
        # callers can't both ``set(...,1)`` and silently drop an increment
        # (lost-update). The 2-day TTL is anchored on the first seed and
        # ``incr`` preserves it. Under contention we may still admit a
        # request or two over ``limit`` (the read above races the incr) —
        # that overrun is bounded by concurrency and intentional; the bug
        # being closed is the unbounded counter-reset, not the soft edge.
        cache.add(cache_key, 0, timeout=86400 * 2)
        try:
            cache.incr(cache_key)
        except ValueError:
            cache.set(cache_key, 1, timeout=86400 * 2)
    except _CACHE_METRIC_ERRORS:
        return True, {}
    return True, {"premium_budget_remaining": max(0, limit - current - 1)}


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
    # Soft daily request budget. The read-then-incr below may admit a
    # request or two over ``limit`` under contention (intentional soft
    # edge), but the increment itself is made atomic via add+incr so the
    # cold-start lost-update (two callers both seeing 0 and both set(1),
    # dropping a count) cannot happen.
    try:
        current = cache.get(cache_key, 0) or 0
        if current >= limit:
            return False, {"budget_exceeded": True, "limit": limit, "period": "day"}
        cache.add(cache_key, 0, timeout=86400 * 2)  # 2 days TTL to cover day boundary
        try:
            cache.incr(cache_key)
        except ValueError:
            cache.set(cache_key, 1, timeout=86400 * 2)
    except _CACHE_METRIC_ERRORS:
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
    # Sentry custom transaction: backs the `ai.gateway.latency` SLO in
    # apps/observability/slo.py. Always paired with finish_transaction
    # in the surrounding wrapper below.
    try:
        from apps.observability.tracing import start_named_transaction, set_transaction_status, finish_transaction
    except (ImportError, AttributeError):
        start_named_transaction = set_transaction_status = finish_transaction = lambda *a, **k: None
    _txn = start_named_transaction("ai.gateway.invoke", op="ai.invoke")
    try:
        return _invoke_inner(task_type, prompt, user_query=user_query, metadata=metadata, response_schema=response_schema)
    except _AI_GATEWAY_RUNTIME_ERRORS:
        set_transaction_status(_txn, "internal_error")
        raise
    finally:
        finish_transaction(_txn)


def _invoke_inner(
    task_type: str | TaskType,
    prompt: str,
    *,
    user_query: str = "",
    metadata: dict[str, Any] | None = None,
    response_schema: str | None = None,
) -> tuple[Any, dict[str, Any]]:
    task = TaskType(task_type) if isinstance(task_type, str) else task_type
    task_key = task.value
    md = metadata or {}
    tenant_id = md.get("tenant_id") or md.get("school_id")
    school_id = md.get("school_id")
    user_id = md.get("user_id")
    if _looks_like_prompt_injection(prompt, user_query):
        request_id = str(uuid4())
        request_date = date.today().isoformat()
        out_meta = {
            "provider": "none",
            "prompt_injection_blocked": True,
            "request_id": request_id,
            "request_date": request_date,
            "task_type": task_key,
            "cost_class": _cost_class_for_tier("none"),
            "user_id": user_id,
        }
        _audit_log(task_key, "none", "", 0, tenant_id, school_id, "blocked", out_meta)
        logger.warning(
            "ai_gateway: blocked likely prompt injection (task=%s)", task_key
        )
        return None, out_meta
    from apps.portal.ai_provider import ai_rules_fallback_allowed

    if not bool(getattr(settings, "AI_GATEWAY_ENABLED", True)):
        request_id = str(uuid4())
        request_date = date.today().isoformat()
        if ai_rules_fallback_allowed():
            result = _rules_invoke_result(
                task_key, user_query or "", prompt, response_schema, md
            )
            out_meta = {
                "provider": "rules",
                "tier": "rules",
                "fallback": True,
                "degraded": response_schema == "guided_assistant",
                "gateway_enabled": False,
                "errors": {"gateway": "disabled"},
                "request_id": request_id,
                "request_date": request_date,
                "task_type": task_key,
                "cost_class": _cost_class_for_tier("rules"),
                "user_id": user_id,
            }
            _audit_log(task_key, "rules", "rules", 0, tenant_id, school_id, "disabled", out_meta)
            return result, out_meta
        out_meta = {
            "provider": "none",
            "fallback": False,
            "gateway_enabled": False,
            "errors": {"gateway": "disabled"},
            "request_id": request_id,
            "request_date": request_date,
            "task_type": task_key,
            "cost_class": _cost_class_for_tier("none"),
            "user_id": user_id,
        }
        _audit_log(task_key, "none", "", 0, tenant_id, school_id, "disabled", out_meta)
        return (
            "AI is disabled and rules fallback is disabled.",
            out_meta,
        )
    tiers_map = _task_tiers()
    backends = tiers_map.get(task_key, ["ollama", "rules"])
    allowed = md.get("allowed_backends")
    rules_allowed_for_call = "rules" in backends
    if allowed is not None and isinstance(allowed, (list, tuple)):
        configured_set = set(backends)
        ordered_allowed: list[str] = []
        for tier_name in allowed:
            normalized = str(tier_name).lower()
            if normalized and normalized not in ordered_allowed:
                ordered_allowed.append(normalized)
        backends = [t for t in ordered_allowed if t in configured_set]
        rules_allowed_for_call = "rules" in backends
        if not backends:
            errors = {"allowed_backends": "no_configured_tiers_matched"}
        else:
            errors: dict[str, str] = {}
    else:
        errors: dict[str, str] = {}
    request_id = str(uuid4())
    request_date = date.today().isoformat()
    budget_ok, budget_meta = _check_and_consume_budget(tenant_id)
    if not budget_ok:
        out_meta = {
            "provider": "none",
            "budget_exceeded": True,
            "request_id": request_id,
            "request_date": request_date,
            "task_type": task_key,
            "cost_class": _cost_class_for_tier("none"),
            "user_id": user_id,
            **budget_meta,
        }
        _audit_log(task_key, "none", "", 0, tenant_id, school_id, "budget_exceeded", out_meta)
        return None, out_meta
    allow_premium = _data_tier_allows_premium(md, prompt=prompt, user_query=user_query)
    timeout_sec = _request_timeout(md)
    start = time.perf_counter()

    for tier in backends:
        # Fast-failover: skip a tier whose circuit is open (recently failing in
        # a row) so a hung/erroring upstream can't burn the request timeout on
        # every call. "rules" is never breakable, so degradation still works.
        if _circuit_is_open(tier):
            errors[tier] = "circuit_open"
            continue
        if tier == "litellm":
            if not allow_premium:
                errors[tier] = "data_tier_disallowed"
                continue
            # Pass 13.C: per-tenant premium spend cap. Skip the tier and try the
            # next one (Ollama) when the daily cap is exhausted.
            premium_ok, premium_meta = _check_and_consume_premium_budget(tenant_id)
            if not premium_ok:
                errors[tier] = "premium_budget_exceeded"
                continue
        text = None
        meta: dict[str, Any] = {}
        if tier == "ollama":
            text, meta = _call_ollama(prompt, metadata=md)
        elif tier == "removed_cloud_provider":
            text, meta = _call_removed_cloud_provider(prompt, metadata=md, timeout_sec=timeout_sec)
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
                        "guided_assistant",
                    )
                ),
                timeout_sec=timeout_sec,
            )
        elif tier == "litellm":
            text, meta = _call_litellm(prompt, metadata=md, timeout_sec=timeout_sec)
        elif tier == "rules":
            elapsed_ms = (time.perf_counter() - start) * 1000
            result = _rules_invoke_result(
                task_key, user_query or "", prompt, response_schema, md
            )
            is_rules_fallback = bool(errors)
            meta = {"fallback": True} if is_rules_fallback else {}
            if response_schema == "guided_assistant":
                meta["degraded"] = True
            if errors:
                meta["errors"] = errors
            meta.update({
                "request_id": request_id,
                "request_date": request_date,
                "task_type": task_key,
                "cost_class": _cost_class_for_tier("rules"),
                "user_id": user_id,
            })
            outcome = "fallback" if is_rules_fallback else "success"
            _audit_log(task_key, "rules", "rules", elapsed_ms, tenant_id, school_id, outcome, meta)
            return result, {"provider": "rules", "tier": "rules", "latency_ms": round(elapsed_ms, 2), **meta}
        if text:
            _circuit_record_success(tier)
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
                    elif response_schema == "guided_assistant" and isinstance(parsed, dict):
                        result = validate_guided_assistant(parsed)
                    else:
                        raise ValueError("invalid_structured_payload")
                except (ValueError, TypeError) as e:
                    logger.warning("Schema validation failed for %s: %s", response_schema, e)
                    schema_validation_failed = True
                    if response_schema == "guided_assistant":
                        result = _rules_invoke_result(
                            task_key, user_query or "", prompt, response_schema, md
                        )
                    else:
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
        # Count this as a real upstream failure for the circuit breaker (policy
        # skips above use `continue` and never reach here).
        _circuit_record_failure(tier)

    elapsed_ms = (time.perf_counter() - start) * 1000
    if ai_rules_fallback_allowed() and rules_allowed_for_call:
        result = _rules_invoke_result(
            task_key, user_query or "", prompt, response_schema, md
        )
        out_meta = {
            "errors": errors,
            "request_id": request_id,
            "request_date": request_date,
            "task_type": task_key,
            "cost_class": _cost_class_for_tier("rules"),
            "user_id": user_id,
            "degraded": response_schema == "guided_assistant",
        }
        _audit_log(task_key, "rules", "rules", elapsed_ms, tenant_id, school_id, "fallback", out_meta)
        return result, {
            "provider": "rules",
            "tier": "rules",
            "latency_ms": round(elapsed_ms, 2),
            "fallback": True,
            **out_meta,
        }
    if response_schema == "guided_assistant":
        from services.ai_unavailable import build_ollama_unavailable_guided

        failure_meta = {
            "errors": errors,
            "request_id": request_id,
            "request_date": request_date,
            "task_type": task_key,
            "cost_class": _cost_class_for_tier("none"),
            "user_id": user_id,
            "ollama_required": True,
            "live_ai_unavailable": True,
        }
        _audit_log(task_key, "none", "", elapsed_ms, tenant_id, school_id, "ollama_required", failure_meta)
        return build_ollama_unavailable_guided(user_query=user_query or ""), {
            "provider": "none",
            "tier": "none",
            "latency_ms": round(elapsed_ms, 2),
            "ollama_required": True,
            "live_ai_unavailable": True,
            **failure_meta,
        }
    failure_meta = {
        "errors": errors,
        "request_id": request_id,
        "request_date": request_date,
        "task_type": task_key,
        "cost_class": _cost_class_for_tier("none"),
        "user_id": user_id,
    }
    _audit_log(task_key, "none", "", elapsed_ms, tenant_id, school_id, "failure", failure_meta)
    return (
        "AI providers are currently unavailable and rules fallback is disabled.",
        {"provider": "none", "errors": errors, "latency_ms": round(elapsed_ms, 2), **failure_meta},
    )
