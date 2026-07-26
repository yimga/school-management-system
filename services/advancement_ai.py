"""
AI drafting for advancement (Wedge 5): donor acknowledgment letters and grant
application drafts. Routes through ``invoke_service_layer_ai`` (RBAC-covered,
closed-fail) per the AI-gateway boundary contract, and ALWAYS degrades to a
deterministic template when the gateway is unavailable — callers never get an
empty string. This is honest AI (it genuinely calls the model when available).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _ack_template(
    donor_name: str,
    school_name: str,
    *,
    amount: Any = None,
    currency: str = "USD",
    campaign_name: str = "",
) -> str:
    gift_line = ""
    if amount:
        gift_line = f" Your gift of {amount} {currency}"
        if campaign_name:
            gift_line += f" toward {campaign_name}"
        gift_line += " makes a direct difference to our students."
    return (
        f"Dear {donor_name},\n\n"
        f"On behalf of everyone at {school_name}, thank you for your generous support."
        f"{gift_line}\n\n"
        f"Your partnership helps us deliver on our mission every day, and we are "
        f"deeply grateful for your trust.\n\n"
        f"With sincere thanks,\n{school_name}"
    )


def _grant_template(
    school_name: str, funder_name: str, program: str, *, amount: Any = None, currency: str = "USD"
) -> str:
    ask = f" We respectfully request {amount} {currency}" if amount else " We respectfully request your support"
    return (
        f"To the {funder_name} review committee,\n\n"
        f"{school_name} is seeking support for {program}.{ask} to fund this work.\n\n"
        f"This program advances educational outcomes for the students we serve. "
        f"We would welcome the opportunity to share detailed budgets, milestones, "
        f"and impact reporting aligned to your funding priorities.\n\n"
        f"Respectfully,\n{school_name}"
    )


def _invoke(prompt: str, *, school, user, user_query: str) -> tuple[str, dict[str, Any]]:
    try:
        from services.ai_copilot_rbac import invoke_service_layer_ai
        from services.ai_gateway import TaskType

        text, meta = invoke_service_layer_ai(
            user=user,
            school=school,
            task_type=TaskType.TEACHER_COMMS_DRAFT,
            prompt=prompt,
            user_query=user_query,
            surface="advancement_ai",
        )
    except (ImportError, AttributeError, TypeError, ValueError) as e:
        logger.debug("advancement_ai invoke skip: %s", e)
        return "", {"provider": "none"}
    if isinstance(meta, dict) and meta.get("outcome") == "permission_refusal":
        return "", meta
    # A gateway rules/unavailable fallback (meta["fallback"]) is a generic
    # "AI temporarily unavailable" chat placeholder, NOT a usable draft. Treat it
    # as a miss so the caller's deterministic _ack_template / _grant_template —
    # which names the donor / program — is used instead. The module contract is
    # "always returns usable text", and the personalized template beats the
    # generic placeholder the gateway returns for chat surfaces.
    if isinstance(meta, dict) and meta.get("fallback"):
        return "", meta
    text = (text or "").strip() if isinstance(text, str) else ""
    return text, (meta or {})


def draft_donor_acknowledgment(
    *,
    school,
    donor_name: str,
    amount: Any = None,
    currency: str = "USD",
    campaign_name: str = "",
    user=None,
) -> tuple[str, dict[str, Any]]:
    """Draft a thank-you/acknowledgment letter. Always returns usable text."""
    facts = [f"School: {school.name}", f"Donor: {donor_name}"]
    if amount:
        facts.append(f"Gift amount: {amount} {currency}")
    if campaign_name:
        facts.append(f"Campaign: {campaign_name}")
    prompt = (
        "Write a warm, sincere, one-paragraph donor thank-you letter for a school. "
        "Be specific and gracious, not effusive. Do not invent facts beyond those given.\n"
        + "\n".join(facts)
    )
    text, meta = _invoke(
        prompt, school=school, user=user, user_query="donor acknowledgment"
    )
    if not text:
        text = _ack_template(
            donor_name, school.name, amount=amount, currency=currency, campaign_name=campaign_name
        )
        meta = {**meta, "provider": meta.get("provider") or "rules", "fallback": True}
    return text, meta


def draft_grant_application(
    *,
    school,
    funder_name: str,
    program: str,
    amount: Any = None,
    currency: str = "USD",
    user=None,
) -> tuple[str, dict[str, Any]]:
    """Draft a short grant application narrative. Always returns usable text."""
    facts = [
        f"School: {school.name}",
        f"Funder: {funder_name}",
        f"Program/purpose: {program}",
    ]
    if amount:
        facts.append(f"Requested amount: {amount} {currency}")
    prompt = (
        "Write a concise, credible 2-paragraph grant application narrative for a "
        "school seeking funding. State the need and the impact. Do not fabricate "
        "metrics or commitments.\n" + "\n".join(facts)
    )
    text, meta = _invoke(
        prompt, school=school, user=user, user_query="grant application draft"
    )
    if not text:
        text = _grant_template(
            school.name, funder_name, program, amount=amount, currency=currency
        )
        meta = {**meta, "provider": meta.get("provider") or "rules", "fallback": True}
    return text, meta
