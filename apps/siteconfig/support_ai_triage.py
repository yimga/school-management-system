"""v4.00.43 — AI triage helper for newly-created support tickets.

Runs a single AI gateway call to suggest a category + a priority bump + a
1-sentence summary for the ticket, persists the structured result to
``ticket.metadata["ai_triage"]`` so operators see it on the detail page.

Soft-fails — any exception or unavailable AI gateway returns ``None`` and
leaves the ticket untouched. Never raises.

Mirrors the v3.27.0 AI center pattern: routes through ``services.ai_helpers``
(NEVER ``services.ai_gateway`` directly) so the architectural-boundary CI
gate stays green.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


_VALID_CATEGORIES = (
    "login",
    "grade",
    "bug",
    "feature",
    "billing",
    "account",
    "other",
)
_VALID_PRIORITIES = ("LOW", "NORMAL", "HIGH", "URGENT")


def _prompt_for_ticket(ticket) -> str:
    """Build a deterministic structured prompt asking for JSON-only output."""
    subject = (getattr(ticket, "subject", "") or "")[:200]
    body = (getattr(ticket, "body", "") or "")[:1200]  # magic-number-allow: ai-message-char-cap
    submission_surface = ""
    template_key = ""
    metadata = getattr(ticket, "metadata", None) or {}
    if isinstance(metadata, dict):
        submission_surface = metadata.get("submission_surface", "") or ""
        template_key = metadata.get("template_key", "") or ""
    return (
        "You are triaging a support ticket. Return ONE JSON object only, no prose, "
        "with keys: category (one of: "
        + ", ".join(_VALID_CATEGORIES)
        + "), priority_suggestion (one of: LOW, NORMAL, HIGH, URGENT), "
        "summary (one sentence under 140 characters), reasoning (one sentence). "
        "Decide priority based on user impact: account lockouts and data loss are URGENT; "
        "billing or grade discrepancies are HIGH; bugs that block a workflow are HIGH; "
        "cosmetic bugs and feature requests are NORMAL. "
        f"submission_surface={submission_surface!r} template_key={template_key!r}\n\n"
        f"Subject: {subject}\n\n"
        f"Body: {body}"
    )


def _parse_ai_response(response: Any) -> dict[str, Any]:
    """Coerce the gateway response into a strict JSON dict; drop bad keys."""
    raw = ""
    if isinstance(response, str):
        raw = response
    elif isinstance(response, dict):
        raw = response.get("text") or response.get("content") or json.dumps(response)
    else:
        raw = str(response or "")

    raw = raw.strip()
    if raw.startswith("```"):
        # Strip optional ```json ... ``` fences.
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
        if raw.endswith("```"):
            raw = raw[:-3].strip()

    try:
        parsed = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        return {}

    if not isinstance(parsed, dict):
        return {}

    category = (parsed.get("category") or "").strip().lower()
    if category not in _VALID_CATEGORIES:
        category = "other"
    priority = (parsed.get("priority_suggestion") or "").strip().upper()
    if priority not in _VALID_PRIORITIES:
        priority = "NORMAL"
    summary = (parsed.get("summary") or "").strip()[:240]  # magic-number-allow: string-truncation-cap
    reasoning = (parsed.get("reasoning") or "").strip()[:480]  # magic-number-allow: string-truncation-cap
    return {
        "category": category,
        "priority_suggestion": priority,
        "summary": summary,
        "reasoning": reasoning,
    }


def run_ai_triage(ticket, *, request=None) -> dict[str, Any] | None:
    """Call the AI gateway, persist structured triage on the ticket.

    Returns the structured triage dict on success, ``None`` when the gateway
    is unavailable or the response was unusable. Never raises.
    """
    try:
        from services.ai_helpers import invoke_with_request
    except ImportError:
        return None

    try:
        result = invoke_with_request(
            task_type="NARRATIVE",
            prompt=_prompt_for_ticket(ticket),
            request=request,
            school=getattr(ticket, "school", None),
            user_query=(getattr(ticket, "subject", "") or "")[:200],
            # NOTE: this prompt is a support-ticket body -- arbitrary free
            # text a parent typed, which routinely contains a child's name
            # and sometimes a safeguarding or medical disclosure. It used to
            # pass content_sensitivity="low_pii_ok", which made
            # services.ai_helpers skip redact_pii precisely when PII had
            # been detected. That opt-out has been removed; the ticket text
            # is now redacted before it reaches any model. Triage needs a
            # category and a priority, not the child.
            #
            # Do NOT add a sensitivity_class here. Unbounded user free text
            # cannot be declared safe for an external model, and
            # services/tests/test_ai_external_sensitivity_call_sites.py
            # fails if this site ever declares one.
            metadata={
                "feature": "support_ai_triage",
            },
            require_available=True,
        )
    except Exception:  # noqa: BLE001 — never break ticket creation
        logger.debug("support_ai_triage: invoke failed", exc_info=True)
        return None

    if not result:
        return None

    response, gateway_meta = result if isinstance(result, tuple) else (result, {})
    parsed = _parse_ai_response(response)
    if not parsed:
        return None

    from django.utils import timezone

    triage = {
        **parsed,
        "model": (gateway_meta or {}).get("model") or "",
        "provider": (gateway_meta or {}).get("provider") or "",
        "generated_at": timezone.now().isoformat(),
        "generated_by": "support_ai_triage_v1",
    }

    try:
        metadata = dict(getattr(ticket, "metadata", None) or {})
        metadata["ai_triage"] = triage
        type(ticket).objects.filter(pk=ticket.pk).update(metadata=metadata)
    except Exception:  # noqa: BLE001 — best-effort persistence
        logger.debug("support_ai_triage: persist failed", exc_info=True)
        return triage

    return triage
