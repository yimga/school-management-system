"""Onboarding-state context for the tenant AI copilot.

The single crucial thing a new-tenant admin's copilot must know is *where they
are in setup* — so that even with NO generative provider configured (the Render
"rules-fallback" posture), the assistant gives genuinely useful next-step
guidance instead of a generic "I can help with…".

This module turns a school's live setup state (from setup_studio's launch-
readiness SOT) into:

  * ``build_onboarding_context_for_ai(school)`` — a compact dict injected into
    the copilot's gateway ``metadata`` so the rules layer / LLM can ground its
    answer in real progress.
  * ``onboarding_insight_cards(school, limit)`` — render-ready insight cards for
    the copilot rail's "insights" feed (next steps, blockers, progress), so the
    rail is useful on first paint before the admin types anything.

Everything is fail-soft: any error yields an empty/neutral result so a copilot
surface never breaks because onboarding state couldn't be read.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Cap how many open steps / blockers we surface so a freshly-provisioned tenant
# (everything open) doesn't produce a wall of guidance.
_MAX_OPEN_STEPS = 6  # magic-number-allow: onboarding-copilot-open-step-surface-cap
_MAX_BLOCKERS = 4  # magic-number-allow: onboarding-copilot-blocker-surface-cap


def _zero_friction(school) -> dict[str, Any]:
    """Best-effort fetch of the launch-readiness payload; {} on any failure."""
    if school is None:
        return {}
    try:
        from apps.setup_studio.zero_friction import get_zero_friction_payload

        return get_zero_friction_payload(school) or {}
    except Exception as exc:  # noqa: BLE001 — onboarding context is best-effort
        logger.debug("onboarding context: zero-friction read failed: %s", exc)
        return {}


def _coerce_label(item: Any) -> str:
    """Pull a human label off a blocker/step dict or object, else str()."""
    if isinstance(item, dict):
        return str(item.get("label") or item.get("title") or item.get("key") or "").strip()
    for attr in ("label", "title", "name", "key"):
        val = getattr(item, attr, None)
        if val:
            return str(val).strip()
    return str(item).strip()


def _coerce_link(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("link") or item.get("url") or "").strip()
    for attr in ("link", "url"):
        val = getattr(item, attr, None)
        if val:
            return str(val).strip()
    return ""


def build_onboarding_context_for_ai(school) -> dict[str, Any]:
    """Compact onboarding snapshot for copilot gateway ``metadata`` injection.

    Returns ``{"onboarding_state": {...}}`` (or ``{}`` when nothing is known) so
    callers can ``metadata.update(build_onboarding_context_for_ai(school))``.
    """
    try:
        payload = _zero_friction(school)
        if not payload:
            return {}
        blockers = payload.get("launch_blockers") or []
        recommended = payload.get("recommended_next")
        state: dict[str, Any] = {
            "launch_ready": bool(payload.get("launch_ready")),
            "health_score": payload.get("health_score"),
            "blockers": [_coerce_label(b) for b in blockers if _coerce_label(b)][:_MAX_BLOCKERS],
            "recommended_next": _coerce_label(recommended) if recommended else "",
        }
        # Drop empty keys so the prompt context stays lean.
        state = {k: v for k, v in state.items() if v not in ("", None, [])}
        return {"onboarding_state": state} if state else {}
    except Exception as exc:  # noqa: BLE001 — never break a copilot invoke
        logger.debug("onboarding context: shaping failed: %s", exc)
        return {}


def onboarding_prompt_preamble(school) -> str:
    """A short natural-language grounding line for the copilot prompt.

    Empty string when there's no onboarding signal (established tenant), so it
    can be unconditionally prepended.
    """
    ctx = build_onboarding_context_for_ai(school).get("onboarding_state")
    if not ctx:
        return ""
    if ctx.get("launch_ready"):
        return ""
    bits = []
    score = ctx.get("health_score")
    if isinstance(score, (int, float)):
        bits.append(f"setup is {int(score)}% complete")
    nxt = ctx.get("recommended_next")
    if nxt:
        bits.append(f"the recommended next step is “{nxt}”")
    blockers = ctx.get("blockers") or []
    if blockers:
        bits.append("open items: " + ", ".join(blockers))
    if not bits:
        return ""
    return (
        "Context: this school is still in first-run setup — "
        + "; ".join(bits)
        + ". Prefer concrete next-step guidance toward going live."
    )


def onboarding_insight_cards(school, *, limit: int = 3) -> list[dict[str, Any]]:
    """Render-ready insight cards for the copilot rail's insights feed.

    Shape mirrors what the rail JS consumes: ``{title, body, href, tone}``.
    Returns [] for an established/launch-ready tenant or on any failure.
    """
    cards: list[dict[str, Any]] = []
    try:
        payload = _zero_friction(school)
        if not payload or payload.get("launch_ready"):
            return []
        # ``source`` mirrors the rail JS contract (cloud|rules) so the insights
        # source badge renders "· guided"; href/tone are extra metadata the rail
        # ignores today but downstream surfaces (wizard index) consume.
        score = payload.get("health_score")
        if isinstance(score, (int, float)):
            cards.append({
                "title": "Setup progress",
                "body": f"Your school is {int(score)}% set up. Finish the guided steps to go live.",
                "href": "",
                "tone": "info",
                "source": "rules",
            })
        recommended = payload.get("recommended_next")
        rec_label = _coerce_label(recommended) if recommended else ""
        if rec_label:
            cards.append({
                "title": "Recommended next",
                "body": rec_label,
                "href": _coerce_link(recommended),
                "tone": "action",
                "source": "rules",
            })
        for blocker in (payload.get("launch_blockers") or [])[:_MAX_BLOCKERS]:
            label = _coerce_label(blocker)
            if not label:
                continue
            cards.append({
                "title": "Before launch",
                "body": label,
                "href": _coerce_link(blocker),
                "tone": "warning",
                "source": "rules",
            })
    except Exception as exc:  # noqa: BLE001 — insights are best-effort
        logger.debug("onboarding insight cards failed: %s", exc)
        return []
    return cards[: max(1, int(limit or 1))]
