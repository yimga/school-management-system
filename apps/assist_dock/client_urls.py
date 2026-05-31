"""Named assist-dock client endpoints — cascade-safe URL SOT for rmc-assist-dock.js."""

from __future__ import annotations

import logging

from django.urls import NoReverseMatch, reverse

logger = logging.getLogger(__name__)

__all__ = ["resolve_assist_dock_client_urls"]


def _reverse(name: str, *, kwargs: dict | None = None) -> str:
    try:
        return reverse(name, kwargs=kwargs or {})
    except NoReverseMatch:
        logger.debug("assist_dock client_urls: NoReverseMatch for %s", name)
        return ""


def resolve_assist_dock_client_urls(request) -> dict[str, str]:
    """Reverse assist_dock namespace paths for the JS dock module."""
    del request  # reserved for future host-aware urlconf
    ai_tpl = _reverse("assist_dock:ai_invoke", kwargs={"action_id": "__ID__"})
    ai_invoke = ai_tpl.replace("__ID__", "{action_id}") if ai_tpl else ""

    return {
        "context": _reverse("assist_dock:context"),
        "context_stream": _reverse("assist_dock:context_stream"),
        "insights": _reverse("assist_dock:insights"),
        "insights_clear": _reverse("assist_dock:insights_clear"),
        "presence_heartbeat": _reverse("assist_dock:presence_heartbeat"),
        "ai_invoke": ai_invoke,
        "share_mint": _reverse("assist_dock:share_mint"),
        "prefs": _reverse("assist_dock:prefs"),
        "wave": _reverse("assist_dock:wave_at"),
        "share_mint_and_email": _reverse("assist_dock:share_mint_and_email"),
    }
