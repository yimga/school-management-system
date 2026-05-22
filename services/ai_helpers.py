"""Platform-wide AI helpers — single integration point for non-migration callers.

`services.ai_gateway.invoke` is the universal abstraction, but every caller
needs the same three things wrapped around it:

1. **Graceful degradation.** When AI is disabled (env / tenant policy /
   provider failure), every helper returns ``None`` and the caller falls
   back to deterministic behaviour. AI must never block a feature.

2. **PII / content sensitivity.** Callers don't always know the right
   value; the helpers infer ``high_pii`` from the inputs when the column
   name or sample contains the obvious PII shapes, so high-PII prompts
   route only to local backends per the tenant's AI policy.

3. **Stable prompt-type tagging.** Every helper supplies a stable
   ``northstar_prompt_type`` so the platform's daily
   ``AIGatewayMetric`` rollup buckets acceptance per surface.

App-level modules (`apps/finance/ai_categorize.py`,
`apps/people/ai_dedup.py`, etc.) call these helpers; they never reach
into ``services.ai_gateway`` directly.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from services.ai_gateway import TaskType  # public re-export for app-level callers

__all__ = ["TaskType", "invoke_with_request", "invoke_with_request_stream", "normalize_gateway_metadata", "record_feedback", "is_ai_available", "looks_like_pii", "redact_pii"]

logger = logging.getLogger(__name__)


def is_ai_available(school: Any | None) -> bool:
    """True when the gateway will actually try to call a model for ``school``."""
    if school is None:
        return False
    try:
        from apps.platform_runtime.ai_providers import get_ai_runtime_config

        cfg = get_ai_runtime_config(school=school)
        return bool(cfg.get("enabled"))
    except Exception:  # noqa: BLE001
        logger.debug("ai_helpers: AI config unavailable", exc_info=True)
        return False


def invoke_task(
    *,
    school: Any | None,
    task_type_name: str,
    prompt: str,
    prompt_type: str,
    content_sensitivity: str = "standard",
    metadata: dict[str, Any] | None = None,
    fallback_task: str = "NARRATIVE",
) -> tuple[str, dict[str, Any]] | None:
    """Generic gateway call. Returns ``(text, meta)`` on success, ``None`` otherwise.

    Used by non-migration AI integrations (finance categorization, people
    dedup, automation suggestions, anomaly narratives, etc.).
    """
    if not is_ai_available(school):
        return None
    try:
        from services.ai_gateway import TaskType, invoke as gateway_invoke

        task_type_value = getattr(TaskType, task_type_name, None) or getattr(TaskType, fallback_task, None)
        if task_type_value is None:
            return None
        meta_out = {
            "school": school,
            "school_id": _school_id(school),
            "northstar_prompt_type": prompt_type,
            "content_sensitivity": content_sensitivity,
        }
        if metadata:
            meta_out.update(metadata)
        text, meta = gateway_invoke(task_type_value, prompt, metadata=meta_out)
        return (text if isinstance(text, str) else str(text or "")), (dict(meta) if isinstance(meta, dict) else {})
    except Exception:  # noqa: BLE001
        logger.debug("ai_helpers: invoke_task failed for %s", task_type_name, exc_info=True)
        return None


def invoke_json_task(
    *,
    school: Any | None,
    task_type_name: str,
    prompt: str,
    prompt_type: str,
    content_sensitivity: str = "standard",
    fallback_task: str = "NARRATIVE",
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Same as ``invoke_task`` but parses a single JSON object from the response.

    Use when you've asked the model for JSON output. Returns ``None`` if
    AI is disabled, the call failed, or no parseable JSON object was found.
    """
    result = invoke_task(
        school=school,
        task_type_name=task_type_name,
        prompt=prompt,
        prompt_type=prompt_type,
        content_sensitivity=content_sensitivity,
        fallback_task=fallback_task,
    )
    if result is None:
        return None
    text, meta = result
    obj = _extract_json(text)
    if obj is None:
        return None
    return obj, meta


_PII_HINTS = ("ssn", "social_security", "national_id", "passport", "dob", "date_of_birth", "email", "phone", "address")
_PII_PATTERNS = (
    re.compile(r"\d{3}-\d{2}-\d{4}"),                 # US SSN
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),          # email
    re.compile(r"\+?\d[\d\s().-]{6,}\d"),             # phone
)


def looks_like_pii(*chunks: str) -> bool:
    """Heuristic PII detector — checks names + values for obvious PII shapes."""
    for chunk in chunks:
        if not chunk:
            continue
        low = chunk.lower()
        if any(hint in low for hint in _PII_HINTS):
            return True
        for pattern in _PII_PATTERNS:
            if pattern.search(chunk):
                return True
    return False


_REDACT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\d{3}-\d{2}-\d{4}"), "[REDACTED-SSN]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[REDACTED-EMAIL]"),
    (re.compile(r"\+?\d[\d\s().-]{6,}\d"), "[REDACTED-PHONE]"),
)


def redact_pii(text: str) -> str:
    """Replace obvious PII shapes with marker tokens.

    Counterpart to ``looks_like_pii``: that one classifies, this one masks.
    Used by callers who want to send the prompt to a lower-sensitivity model
    tier or log the prompt for audit without leaking real PII. Heuristic —
    not exhaustive — covers email, US-shape SSN, and phone-like sequences.
    """
    if not text:
        return text
    out = text
    for pattern, replacement in _REDACT_PATTERNS:
        out = pattern.sub(replacement, out)
    return out


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    match = _JSON_RE.search(text)
    if match is None:
        return None
    try:
        obj = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _school_id(school: Any | None) -> str | None:
    if school is None:
        return None
    pk = getattr(school, "pk", None)
    return str(pk) if pk is not None else None


def normalize_gateway_metadata(
    metadata: dict[str, Any] | None,
    *,
    request: Any | None = None,
    school: Any | None = None,
) -> dict[str, Any]:
    """Build the canonical metadata dict the gateway expects.

    Pulls school/user/country off the request when the caller hasn't already
    populated them. This is the single source of truth for gateway metadata
    shape — every app-level AI call must route through this helper rather
    than reaching into ``apps.portal.ai_provider``.
    """
    md = dict(metadata or {})
    if request is not None and md.get("request") is None:
        md["request"] = request
    request = md.get("request") or request
    school = md.get("school") or school or getattr(request, "school", None)
    if school is not None:
        md.setdefault("school", school)
    if md.get("school_id") is None and school is not None:
        school_id = getattr(school, "pk", None) or getattr(school, "id", None)
        if school_id is not None:
            md["school_id"] = str(school_id)
    if md.get("tenant_id") is None and md.get("school_id") is not None:
        md["tenant_id"] = str(md["school_id"])
    if md.get("country_code") in (None, "") and school is not None:
        country_code = getattr(school, "country_code", None) or getattr(
            getattr(school, "default_region", None), "code", None
        )
        if country_code:
            md["country_code"] = country_code
    if md.get("user_id") is None and request is not None:
        user = getattr(request, "user", None)
        user_id = getattr(user, "pk", None) or getattr(user, "id", None)
        if user_id is not None:
            md["user_id"] = str(user_id)
    if md.get("role") is None and request is not None:
        user = getattr(request, "user", None)
        role = (
            getattr(user, "role", None)
            or getattr(user, "portal_role", None)
            or getattr(user, "user_type", None)
        )
        if role is not None:
            md["role"] = role
    return md


def invoke_with_request(
    *,
    task_type: Any,
    prompt: str,
    request: Any | None = None,
    school: Any | None = None,
    user_query: str = "",
    metadata: dict[str, Any] | None = None,
    response_schema: str | None = None,
    require_available: bool = True,
) -> tuple[Any, dict[str, Any]] | None:
    """Single canonical gateway entry-point for app-level callers that have a request.

    Wraps ``services.ai_gateway.invoke`` with:
      * graceful degradation (``None`` when AI policy disables the call),
      * automatic metadata normalization via ``normalize_gateway_metadata``,
      * flexible ``task_type`` (string or ``TaskType`` member).

    Set ``require_available=False`` when the caller wants to attempt the
    gateway even if ``is_ai_available`` reports off — the gateway itself
    has its own degradation path (``provider="none"``) that some surfaces
    prefer to handle inline rather than short-circuiting on policy.

    App code (views, consumers, Celery tasks) must NEVER import
    ``services.ai_gateway`` directly — always go through this helper. The
    only legitimate direct importers are infrastructure modules under
    ``services/`` itself, ``apps/portal/ai_provider.py`` (low-level
    provider tier), and the explicit gateway/metrics surfaces.
    """
    resolved_school = school
    if resolved_school is None and request is not None:
        resolved_school = getattr(request, "school", None)
    if require_available and not is_ai_available(resolved_school):
        return None
    try:
        from services.ai_gateway import TaskType, invoke as gateway_invoke

        if isinstance(task_type, str):
            try:
                resolved_task = TaskType(task_type)
            except ValueError:
                resolved_task = getattr(TaskType, task_type, None) or getattr(
                    TaskType, task_type.upper(), None
                )
                if resolved_task is None:
                    return None
        else:
            resolved_task = task_type
        md = normalize_gateway_metadata(metadata, request=request, school=resolved_school)
        if looks_like_pii(prompt, user_query) and md.get("content_sensitivity") != "low_pii_ok":
            prompt = redact_pii(prompt)
            if user_query:
                user_query = redact_pii(user_query)
            md["pii_redacted"] = True
        return gateway_invoke(
            resolved_task,
            prompt,
            user_query=user_query,
            metadata=md,
            response_schema=response_schema,
        )
    except Exception:  # noqa: BLE001
        logger.debug("ai_helpers: invoke_with_request failed", exc_info=True)
        return None


def invoke_with_request_stream(
    *,
    task_type: Any,
    prompt: str,
    request: Any | None = None,
    school: Any | None = None,
    user_query: str = "",
    metadata: dict[str, Any] | None = None,
    require_available: bool = True,
):
    """Streaming sibling of ``invoke_with_request`` (v3.59.2).

    Yields ``("chunk", text)`` tuples as model tokens arrive, then exactly ONE
    ``("done", metadata)`` tuple. On any error, yields one ``("error", code)``
    tuple followed by a final ``("done", metadata)`` so consumers can always
    close cleanly.

    Same PII / policy / school-resolution rules as the non-streaming sibling.
    Returns a generator. Returns ``None`` when AI policy disables the call
    (consumers should fall back to a guided / unavailable UX).
    """
    resolved_school = school
    if resolved_school is None and request is not None:
        resolved_school = getattr(request, "school", None)
    if require_available and not is_ai_available(resolved_school):
        return None

    try:
        from services.ai_gateway import TaskType
        from services.ai_gateway_streaming import invoke_stream

        if isinstance(task_type, str):
            try:
                resolved_task = TaskType(task_type)
            except ValueError:
                resolved_task = getattr(TaskType, task_type, None) or getattr(
                    TaskType, task_type.upper(), None
                )
                if resolved_task is None:
                    return None
        else:
            resolved_task = task_type

        md = normalize_gateway_metadata(metadata, request=request, school=resolved_school)
        local_prompt = prompt
        local_user_query = user_query
        if looks_like_pii(local_prompt, local_user_query) and md.get("content_sensitivity") != "low_pii_ok":
            local_prompt = redact_pii(local_prompt)
            if local_user_query:
                local_user_query = redact_pii(local_user_query)
            md["pii_redacted"] = True

        return invoke_stream(
            resolved_task,
            local_prompt,
            metadata=md,
            user_query=local_user_query,
        )
    except Exception:  # noqa: BLE001
        logger.debug("ai_helpers: invoke_with_request_stream failed", exc_info=True)
        return None


def record_feedback(
    *,
    school: Any | None,
    task_type_name: str,
    tier: str = "unknown",
    accepted: bool | None = None,
    manual_correction: bool | None = None,
    request_id: str | None = None,
) -> None:
    """Forward an operator accept/override decision to the daily AIGatewayMetric rollup.

    No-op when the gateway is unavailable. Use after the user clicks
    "accept", "edit", or "dismiss" on an AI-generated suggestion so the
    platform learns which surfaces convert.
    """
    try:
        from services.ai_gateway import TaskType, record_feedback as _record

        task_type_value = getattr(TaskType, task_type_name, None) or TaskType.NARRATIVE
        _record(
            task_type_value,
            tier,
            tenant_id=_school_id(school),
            school_id=_school_id(school),
            accepted=accepted,
            manual_correction=manual_correction,
            request_id=request_id,
        )
    except Exception:  # noqa: BLE001
        logger.debug("ai_helpers: record_feedback skipped", exc_info=True)
