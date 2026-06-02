"""v4.00.49 — AI drafted-reply helper for support tickets.

Generates a polite, on-brand first-draft response for an open ticket. The
operator can accept-as-is, edit-and-send, or discard. We deliberately do NOT
auto-send — the operator is always in the loop. The draft is persisted to
``ticket.metadata["ai_draft_reply"]`` so the queue page can surface a chip
and the detail page can render the textarea pre-filled.

Mirrors :mod:`apps.siteconfig.support_ai_triage`:
  * Routes through ``services.ai_helpers.invoke_with_request`` (NEVER
    ``services.ai_gateway`` directly).
  * Soft-fails — returns ``None`` on any error.
  * Operator accept / edit / discard signals fan out via
    ``services.ai_helpers.record_feedback`` so the gateway learns which
    suggestions land.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


_TONE_CHOICES = ("warm", "neutral", "formal")
_MAX_DRAFT_CHARS = 1600  # magic-number-allow: ai-message-char-cap


def _prompt_for_draft(ticket, tone: str) -> str:
    subject = (getattr(ticket, "subject", "") or "")[:200]
    body = (getattr(ticket, "body", "") or "")[:1200]  # magic-number-allow: ai-message-char-cap
    category = ""
    metadata = getattr(ticket, "metadata", None) or {}
    if isinstance(metadata, dict):
        triage = metadata.get("ai_triage") or {}
        if isinstance(triage, dict):
            category = (triage.get("category") or "")[:40]
    return (
        "You are drafting a first-response reply from a school management platform's "
        "support team. Return ONE JSON object only, no prose, with keys: "
        "draft_text (plain text, under "
        f"{_MAX_DRAFT_CHARS} characters; greeting + acknowledgement + next step + sign-off "
        "with the placeholder [Your name]), "
        "tone (one of: warm, neutral, formal), "
        "confidence (low / medium / high), "
        "next_step_hint (one short sentence describing what the operator should do next). "
        f"Use a {tone} tone. Do not promise a fix; acknowledge, set expectations, and "
        "ask for any missing information. Do not include disclaimers, legalese, or marketing.\n\n"
        f"Ticket category: {category}\n\n"
        f"Subject: {subject}\n\n"
        f"Body: {body}"
    )


def _parse_ai_response(response: Any) -> dict[str, Any]:
    raw = ""
    if isinstance(response, str):
        raw = response
    elif isinstance(response, dict):
        raw = response.get("text") or response.get("content") or json.dumps(response)
    else:
        raw = str(response or "")

    raw = raw.strip()
    if raw.startswith("```"):
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

    draft_text = (parsed.get("draft_text") or "").strip()[:_MAX_DRAFT_CHARS]
    if not draft_text:
        return {}
    tone = (parsed.get("tone") or "").strip().lower()
    if tone not in _TONE_CHOICES:
        tone = "warm"
    confidence = (parsed.get("confidence") or "").strip().lower()
    if confidence not in ("low", "medium", "high"):
        confidence = "medium"
    next_step_hint = (parsed.get("next_step_hint") or "").strip()[:280]  # magic-number-allow: string-truncation-cap
    return {
        "draft_text": draft_text,
        "tone": tone,
        "confidence": confidence,
        "next_step_hint": next_step_hint,
    }


def run_ai_draft_reply(ticket, *, request=None, tone: str = "warm") -> dict[str, Any] | None:
    """Call the AI gateway, persist a drafted reply on the ticket.

    Returns the structured draft dict on success; ``None`` when the gateway
    is unavailable or the response was unusable. Never raises.
    """
    try:
        from services.ai_helpers import invoke_with_request
    except ImportError:
        return None

    tone = (tone or "").lower().strip()
    if tone not in _TONE_CHOICES:
        tone = "warm"

    try:
        result = invoke_with_request(
            task_type="NARRATIVE",
            prompt=_prompt_for_draft(ticket, tone),
            request=request,
            school=getattr(ticket, "school", None),
            user_query=(getattr(ticket, "subject", "") or "")[:200],
            metadata={
                "feature": "support_ai_draft_reply",
                "content_sensitivity": "low_pii_ok",
            },
            require_available=True,
        )
    except Exception:  # noqa: BLE001 — never break ticket actions
        logger.debug("support_ai_draft_reply: invoke failed", exc_info=True)
        return None

    if not result:
        return None

    response, gateway_meta = result if isinstance(result, tuple) else (result, {})
    parsed = _parse_ai_response(response)
    if not parsed:
        return None

    from django.utils import timezone

    draft = {
        **parsed,
        "model": (gateway_meta or {}).get("model") or "",
        "provider": (gateway_meta or {}).get("provider") or "",
        "generated_at": timezone.now().isoformat(),
        "generated_by": "support_ai_draft_reply_v1",
    }

    try:
        metadata = dict(getattr(ticket, "metadata", None) or {})
        metadata["ai_draft_reply"] = draft
        type(ticket).objects.filter(pk=ticket.pk).update(metadata=metadata)
    except Exception:  # noqa: BLE001 — best-effort persistence
        logger.debug("support_ai_draft_reply: persist failed", exc_info=True)
        return draft

    return draft


def record_draft_feedback(ticket, *, decision: str, edited: bool, applied_text: str) -> None:
    """Append the operator's decision to ``metadata["ai_draft_feedback"]``.

    ``decision`` is one of ``accepted``, ``edited``, ``discarded``. We cap the
    audit list at 20 entries so a busy ticket doesn't bloat the JSON blob.
    Also routes ``services.ai_helpers.record_feedback`` so the gateway sees the
    acceptance signal.
    """
    try:
        from django.utils import timezone

        metadata = dict(getattr(ticket, "metadata", None) or {})
        feedback_log = list(metadata.get("ai_draft_feedback") or [])
        feedback_log.append(
            {
                "decision": decision,
                "edited": bool(edited),
                "applied_chars": len(applied_text or ""),
                "at": timezone.now().isoformat(),
            }
        )
        metadata["ai_draft_feedback"] = feedback_log[-20:]
        type(ticket).objects.filter(pk=ticket.pk).update(metadata=metadata)
    except Exception:  # noqa: BLE001 — audit must never block reply send
        logger.debug("support_ai_draft_reply: feedback persist failed", exc_info=True)

    try:
        from services.ai_helpers import record_feedback

        record_feedback(
            getattr(ticket, "school", None),
            task_type_name="NARRATIVE",
            tier="support_ai_draft_reply",
            accepted=decision in ("accepted", "edited"),
        )
    except Exception:  # noqa: BLE001 — gateway feedback is best-effort
        logger.debug("support_ai_draft_reply: gateway record_feedback failed", exc_info=True)
