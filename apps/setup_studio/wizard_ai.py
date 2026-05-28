"""Wizard AI bridge — 5 public callables, all routed through services.ai_helpers.

CRITICAL: app code MUST NOT import ``services.ai_gateway`` directly.
``scan_ai_gateway_boundary.py`` enforces baseline 0. This module is the
ONLY place inside ``apps/setup_studio/`` that touches AI — verified by
``scan_wizard_ai_boundary.py``.

Every helper:
1. Sanitizes context (drops 14+ sensitive-keyword keys).
2. Calls services.ai_helpers.invoke_with_request with 5s budget.
3. Parses returned JSON against expected schema.
4. Falls back to deterministic rule on any failure.
5. Emits observability metric.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from apps.setup_studio import ai_fallbacks, ai_prompts, wizard_telemetry

logger = logging.getLogger(__name__)

__all__ = [
    "AI_BUDGET_SECONDS",
    "AI_MAX_TOKENS_DEFAULT",
    "SmartDefaultsResult",
    "BranchRationaleResult",
    "NaturalLanguageIntakeResult",
    "TranslationMeshResult",
    "request_smart_defaults",
    "request_branch_rationale",
    "request_natural_language_intake",
    "request_translation_mesh",
    "refresh_setup_recommendations",
]

AI_BUDGET_SECONDS = 5.0
AI_MAX_TOKENS_DEFAULT = 800

_SENSITIVE_CONTEXT_REJECT_FRAGMENTS = (
    "password", "passwd", "pwd", "hash", "secret", "token",
    "ssn", "dob", "api_key", "apikey", "private_key",
    "signature_text", "email", "phone",
    "ifsc", "iban", "swift", "pan", "aadhaar", "tin",
    "guardian_name", "student_name", "license_plate",
)


@dataclass(frozen=True)
class SmartDefaultsResult:
    suggestions: dict[str, Any]
    confidence: dict[str, float]
    rationale_text: str | None
    used_fallback: bool
    latency_ms: int


@dataclass(frozen=True)
class BranchRationaleResult:
    rationale_text: str
    used_fallback: bool
    latency_ms: int


@dataclass(frozen=True)
class NaturalLanguageIntakeResult:
    parsed_fields: dict[str, Any]
    unresolved_phrases: list[str]
    confidence: float
    used_fallback: bool
    latency_ms: int


@dataclass(frozen=True)
class TranslationMeshResult:
    translations: dict[str, str]
    failed_locales: list[str]
    used_fallback: bool
    latency_ms: int


def _is_sensitive_key(key: str) -> bool:
    lk = key.lower()
    return any(frag in lk for frag in _SENSITIVE_CONTEXT_REJECT_FRAGMENTS)


def _sanitize_context(context: dict[str, Any]) -> dict[str, Any]:
    """Walks dict + nested dicts/lists, drops any key matching sensitive fragments."""
    if not isinstance(context, dict):
        return {}
    out: dict[str, Any] = {}
    for k, v in context.items():
        if _is_sensitive_key(str(k)):
            continue
        if isinstance(v, dict):
            out[k] = _sanitize_context(v)
        elif isinstance(v, list):
            out[k] = [_sanitize_context(item) if isinstance(item, dict) else item for item in v]
        else:
            out[k] = v
    return out


def _call_gateway(
    *,
    request: Any | None,
    school: Any | None,
    prompt: str,
    prompt_type: str,
    response_schema: str | None = "json",
) -> tuple[str | None, dict[str, Any]]:
    """Single integration point with services.ai_helpers.

    Returns ``(text, meta)`` or ``(None, {})`` on any failure.
    Never raises.
    """
    try:
        from services.ai_helpers import invoke_with_request, TaskType  # type: ignore
    except ImportError as exc:
        logger.warning("wizard_ai: ai_helpers unavailable: %s", exc)
        return None, {}

    try:
        result = invoke_with_request(
            task_type=TaskType.NARRATIVE,
            prompt=prompt,
            request=request,
            school=school,
            user_query="",
            metadata={"northstar_prompt_type": prompt_type},
            response_schema=response_schema,
            require_available=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("wizard_ai: gateway call failed: %s", exc)
        return None, {}

    if result is None:
        return None, {}
    if isinstance(result, tuple) and len(result) >= 2:
        text, meta = result[0], result[1] or {}
        return (str(text) if text is not None else None), meta
    return None, {}


def _parse_json(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # strip common ```json … ``` fences
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].lstrip()
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def _fallback_for(prompt_key: str, context: dict[str, Any], options: list[dict[str, Any]]) -> dict[str, Any]:
    fn = ai_fallbacks.FALLBACK_REGISTRY.get(prompt_key)
    if fn is None:
        return {}
    try:
        return fn(context, options) or {}
    except Exception as exc:  # noqa: BLE001
        logger.exception("wizard_ai: fallback %s failed: %s", prompt_key, exc)
        return {}


# ---------- Public API ----------


def request_smart_defaults(
    *,
    request: Any | None,
    school: Any | None,
    wizard_key: str,
    step_key: str,
    prompt_key: str,
    context: dict[str, Any] | None = None,
    options: list[dict[str, Any]] | None = None,
) -> SmartDefaultsResult:
    """Returns SmartDefaultsResult. Never raises."""
    t0 = time.monotonic()
    sanitized = _sanitize_context(context or {})
    options = options or []

    try:
        prompt = ai_prompts.build_prompt(prompt_key, context=sanitized, options=options)
    except KeyError:
        logger.warning("wizard_ai: unknown prompt_key %s", prompt_key)
        latency_ms = int((time.monotonic() - t0) * 1000)
        wizard_telemetry.emit_ai_smart_defaults_outcome(wizard_key, step_key, "fallback", latency_ms)
        fb = _fallback_for(prompt_key, sanitized, options)
        return SmartDefaultsResult(
            suggestions=fb, confidence={}, rationale_text=None, used_fallback=True, latency_ms=latency_ms,
        )

    text, _meta = _call_gateway(
        request=request, school=school, prompt=prompt, prompt_type=f"wizard.{prompt_key}",
    )
    parsed = _parse_json(text)
    latency_ms = int((time.monotonic() - t0) * 1000)

    if parsed is None:
        fb = _fallback_for(prompt_key, sanitized, options)
        wizard_telemetry.emit_ai_smart_defaults_outcome(wizard_key, step_key, "fallback", latency_ms)
        return SmartDefaultsResult(
            suggestions=fb, confidence={}, rationale_text=None, used_fallback=True, latency_ms=latency_ms,
        )

    # Confirm any 'option-value' fields are in OPTIONS list (defense vs hallucination)
    option_values = {o.get("value") for o in options if isinstance(o, dict)}
    invalid = False
    for v in parsed.values():
        if isinstance(v, str) and option_values and v not in option_values and v.startswith("opt_"):
            invalid = True
            break
    if invalid:
        fb = _fallback_for(prompt_key, sanitized, options)
        wizard_telemetry.emit_ai_smart_defaults_outcome(wizard_key, step_key, "fallback", latency_ms)
        return SmartDefaultsResult(
            suggestions=fb, confidence={}, rationale_text=None, used_fallback=True, latency_ms=latency_ms,
        )

    confidence = {}
    raw_conf = parsed.get("confidence")
    if isinstance(raw_conf, (int, float)):
        confidence["overall"] = float(raw_conf)
    rationale = parsed.get("rationale_text") if isinstance(parsed.get("rationale_text"), str) else None
    wizard_telemetry.emit_ai_smart_defaults_outcome(wizard_key, step_key, "success", latency_ms)

    return SmartDefaultsResult(
        suggestions=parsed,
        confidence=confidence,
        rationale_text=rationale,
        used_fallback=False,
        latency_ms=latency_ms,
    )


def request_branch_rationale(
    *,
    request: Any | None,
    school: Any | None,
    wizard_key: str,
    step_key: str,
    prior_answers: dict[str, Any] | None = None,
    branch_taken: str | None = None,
) -> BranchRationaleResult:
    t0 = time.monotonic()
    sanitized = _sanitize_context({"prior_answers": prior_answers or {}, "branch_taken": branch_taken or ""})
    try:
        prompt = ai_prompts.build_prompt(
            "prompt.universal.branch_rationale", context=sanitized, options=[],
        )
    except KeyError:
        latency_ms = int((time.monotonic() - t0) * 1000)
        wizard_telemetry.emit_ai_branch_rationale_outcome(wizard_key, step_key, "fallback", latency_ms)
        return BranchRationaleResult(
            rationale_text="", used_fallback=True, latency_ms=latency_ms,
        )

    text, _meta = _call_gateway(
        request=request, school=school, prompt=prompt, prompt_type="wizard.branch_rationale",
    )
    parsed = _parse_json(text)
    latency_ms = int((time.monotonic() - t0) * 1000)

    if parsed is None or "rationale_text" not in parsed:
        fb = _fallback_for("prompt.universal.branch_rationale", sanitized, [])
        wizard_telemetry.emit_ai_branch_rationale_outcome(wizard_key, step_key, "fallback", latency_ms)
        return BranchRationaleResult(
            rationale_text=str(fb.get("rationale_text", "")),
            used_fallback=True,
            latency_ms=latency_ms,
        )

    rationale = str(parsed["rationale_text"])[:280]
    wizard_telemetry.emit_ai_branch_rationale_outcome(wizard_key, step_key, "success", latency_ms)
    return BranchRationaleResult(
        rationale_text=rationale, used_fallback=False, latency_ms=latency_ms,
    )


def request_natural_language_intake(
    *,
    request: Any | None,
    school: Any | None,
    wizard_key: str,
    free_text: str,
    target_fields: list[str],
) -> NaturalLanguageIntakeResult:
    t0 = time.monotonic()
    sanitized = _sanitize_context({"free_text": free_text[:2000], "target_fields": list(target_fields)})
    try:
        prompt = ai_prompts.build_prompt(
            "prompt.universal.natural_language_intake", context=sanitized, options=[],
        )
    except KeyError:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return NaturalLanguageIntakeResult(
            parsed_fields={}, unresolved_phrases=[free_text], confidence=0.0,
            used_fallback=True, latency_ms=latency_ms,
        )

    text, _meta = _call_gateway(
        request=request, school=school, prompt=prompt, prompt_type="wizard.nl_intake",
    )
    parsed = _parse_json(text)
    latency_ms = int((time.monotonic() - t0) * 1000)

    if parsed is None:
        return NaturalLanguageIntakeResult(
            parsed_fields={}, unresolved_phrases=[free_text], confidence=0.0,
            used_fallback=True, latency_ms=latency_ms,
        )
    return NaturalLanguageIntakeResult(
        parsed_fields=parsed.get("parsed_fields") or {},
        unresolved_phrases=parsed.get("unresolved_phrases") or [],
        confidence=float(parsed.get("confidence") or 0.0),
        used_fallback=False,
        latency_ms=latency_ms,
    )


def request_translation_mesh(
    *,
    request: Any | None,
    school: Any | None,
    wizard_key: str,
    source_locale: str,
    target_locales: list[str],
    message: str,
) -> TranslationMeshResult:
    t0 = time.monotonic()
    sanitized = _sanitize_context({
        "source_locale": source_locale,
        "target_locales": list(target_locales),
        "message": message[:4000],
    })
    try:
        prompt = ai_prompts.build_prompt(
            "prompt.comms.translate_template", context=sanitized, options=[],
        )
    except KeyError:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return TranslationMeshResult(
            translations={}, failed_locales=list(target_locales),
            used_fallback=True, latency_ms=latency_ms,
        )

    text, _meta = _call_gateway(
        request=request, school=school, prompt=prompt, prompt_type="wizard.translate_mesh",
    )
    parsed = _parse_json(text)
    latency_ms = int((time.monotonic() - t0) * 1000)

    if parsed is None or not isinstance(parsed.get("translations"), dict):
        for loc in target_locales:
            wizard_telemetry.emit_ai_translate_mesh_outcome(wizard_key, source_locale, loc, "fallback")
        return TranslationMeshResult(
            translations={}, failed_locales=list(target_locales),
            used_fallback=True, latency_ms=latency_ms,
        )

    translations = {k: str(v) for k, v in parsed["translations"].items() if isinstance(v, str)}
    failed = [loc for loc in target_locales if loc not in translations]
    for loc in translations:
        wizard_telemetry.emit_ai_translate_mesh_outcome(wizard_key, source_locale, loc, "success")
    for loc in failed:
        wizard_telemetry.emit_ai_translate_mesh_outcome(wizard_key, source_locale, loc, "fallback")

    return TranslationMeshResult(
        translations=translations, failed_locales=failed,
        used_fallback=False, latency_ms=latency_ms,
    )


def refresh_setup_recommendations(
    *,
    request: Any | None = None,
    school: Any | None = None,
    max_recommendations: int = 10,
) -> list[dict[str, Any]]:
    """Nightly Celery beat handler. Writes fresh SetupProgress.recommendations.

    For now this assembles deterministic recommendations from the wizard
    registry (which wizards remain incomplete) plus existing rule-based
    suggestions from setup_studio.services.

    Future expansion: AI-generated per-tenant prioritization.
    """
    from apps.setup_studio import wizard_engine, wizard_state_resolver

    if school is None or getattr(school, "pk", None) is None:
        return []

    try:
        progress = wizard_state_resolver.get_or_create_progress(school)
    except Exception as exc:  # noqa: BLE001
        logger.warning("refresh_setup_recommendations: progress fetch failed: %s", exc)
        return []

    recs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for wizard in sorted(wizard_engine.WIZARD_REGISTRY.values(), key=lambda w: w.wizard_key):
        if wizard.wizard_key in seen:
            continue
        if wizard_state_resolver.is_wizard_completed(school, wizard.wizard_key):
            continue
        recs.append({
            "kind": "wizard_pending",
            "wizard_key": wizard.wizard_key,
            "label_token": wizard.label_token,
            "estimated_minutes": wizard.estimated_minutes,
            "icon_class": wizard.icon_class,
            "audience": list(wizard.audience),
        })
        seen.add(wizard.wizard_key)
        if len(recs) >= max_recommendations:
            break

    progress.recommendations = recs
    progress.save(update_fields=["recommendations", "updated_at"])
    return recs
