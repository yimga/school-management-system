"""AI-assisted workflow failure diagnosis for Flight Deck self-healing."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from apps.platform_runtime.workflow_error_classifier import ErrorFingerprint

logger = logging.getLogger(__name__)

_HEALING_AI_SCHEMA = (
    '{"title":"<short title>","cause":"<one sentence>","plan":["<step1>"],'
    '"recommended_chain":["<auto_fix_kind>"],'
    '"confidence":"low|medium|high","auto_fix_available":true|false}'
)


def _error_fields(run: Any) -> tuple[str, str]:
    err = getattr(run, "error_summary", None) or {}
    error_type = ""
    error_message = ""
    if isinstance(err, dict):
        error_type = str(err.get("type") or err.get("code") or "")
        error_message = str(err.get("message") or err.get("detail") or "")
    return error_type, error_message


def _parse_ai_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _sanitize_chain(raw: Any) -> list[str]:
    from apps.platform_runtime.workflow_fix_handlers import auto_fix_kind_is_executable

    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        kind = str(item or "").strip()
        if kind and auto_fix_kind_is_executable(kind) and kind not in out:
            out.append(kind)
    return out


def ai_diagnosis_for_run(
    *,
    run: Any,
    fingerprint: ErrorFingerprint,
    request: Any | None = None,
) -> dict[str, Any] | None:
    """Best-effort AI diagnosis. Returns None when AI is unavailable."""

    if fingerprint.confidence == "high" and fingerprint.recommended_chain:
        return None

    workflow_key = str(getattr(run, "workflow_key", "") or "")
    error_type, error_message = _error_fields(run)

    prompt = (
        "A platform workflow failed. Diagnose the failure and suggest remediation.\n\n"
        f"workflow_key: {workflow_key}\n"
        f"error_type: {error_type}\n"
        f"error_message: {error_message[:600]}\n"
        f"rule_title: {fingerprint.human_title}\n"
        f"rule_cause: {fingerprint.human_cause}\n"
        f"rule_chain: {', '.join(fingerprint.recommended_chain)}\n\n"
        "Respond with JSON only matching this schema:\n"
        f"{_HEALING_AI_SCHEMA}\n"
        "Use only known auto_fix_kind values when recommending a chain: "
        "requeue_provision, retry_failed_step, resume_from_checkpoint, "
        "replay_webhook, clear_stale_lock, retry_once_with_backoff, "
        "retry_after_rate_limit, refresh_oauth_token_and_retry, "
        "repair_tenant_schema_drift, run_tenant_migrations."
    )

    try:
        from apps.platform_runtime.ai_workflow_invoker import invoke_with_workflow_context
    except Exception:
        return None

    try:
        # rbac-copilot-allow: operator-staff-workflow-healing-diagnosis-unattended-fallback
        result = invoke_with_workflow_context(
            request=request,
            task_type="observability_assistant",
            prompt=prompt,
            workflow_key=workflow_key,
            metadata={"purpose": "workflow_healing_diagnosis"},
            require_available=False,
        )
    except Exception:
        logger.warning("workflow_healing_ai_invoke_failed key=%s", workflow_key)
        return None

    if not result:
        return None

    response, _meta = result
    text = ""
    if isinstance(response, dict):
        text = str(response.get("text") or response.get("output") or "")
    else:
        text = str(response)

    parsed = _parse_ai_json(text)
    if not parsed:
        return None

    chain = _sanitize_chain(parsed.get("recommended_chain"))
    plan = parsed.get("plan")
    if not isinstance(plan, list):
        plan = [str(parsed.get("human_action") or fingerprint.human_fix_summary or "Apply fix")]

    return {
        "title": str(parsed.get("title") or fingerprint.human_title)[:160],
        "cause": str(parsed.get("cause") or fingerprint.human_cause)[:400],
        "plan": [str(step)[:120] for step in plan[:6]],
        "recommended_chain": chain,
        "confidence": str(parsed.get("confidence") or "medium")[:16],
        "source": "ai_assisted",
        "auto_fix_available": bool(chain or parsed.get("auto_fix_available")),
    }


def enrich_fingerprint_with_ai(
    *,
    run: Any,
    fingerprint: ErrorFingerprint,
    request: Any | None = None,
) -> ErrorFingerprint:
    """Augment a rule-based fingerprint with AI diagnosis when helpful."""

    ai = ai_diagnosis_for_run(run=run, fingerprint=fingerprint, request=request)
    if not ai:
        return fingerprint

    chain = list(fingerprint.recommended_chain or [])
    for kind in ai.get("recommended_chain") or []:
        if kind not in chain:
            chain.append(kind)

    fingerprint.human_title = str(ai.get("title") or fingerprint.human_title)
    fingerprint.human_cause = str(ai.get("cause") or fingerprint.human_cause)
    if ai.get("recommended_chain"):
        fingerprint.recommended_chain = chain
    fingerprint.confidence = str(ai.get("confidence") or fingerprint.confidence)
    fingerprint.diagnosis_source = "ai_assisted"
    if ai.get("auto_fix_available") and chain:
        fingerprint.safe_for_autopilot = fingerprint.safe_for_autopilot or (
            fingerprint.confidence == "high"
        )
    fingerprint.human_fix_summary = (
        " → ".join(str(step) for step in (ai.get("plan") or [])[:4])
        or fingerprint.human_fix_summary
    )
    return fingerprint
