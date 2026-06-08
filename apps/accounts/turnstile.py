"""Cloudflare Turnstile verification for the login bot-challenge.

Env-gated: with no ``TURNSTILE_SITE_KEY`` / ``TURNSTILE_SECRET_KEY`` configured
the challenge is inert and ``verify_turnstile`` returns ``True`` so sign-in is
never blocked before the operator wires Cloudflare keys.

Fails **open** on Cloudflare unreachability (network error / timeout / bad
JSON) so a Cloudflare outage cannot lock every legitimate user out — the
always-on ``login_guard`` lockout still applies as the hard backstop. A
present-but-invalid token fails **closed** (that is the bot signal we want).
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_VERIFY_TIMEOUT_SECONDS = 5


def turnstile_enabled() -> bool:
    """True only when BOTH the public site key and the secret key are set."""
    return bool(
        (getattr(settings, "TURNSTILE_SITE_KEY", "") or "").strip()
        and (getattr(settings, "TURNSTILE_SECRET_KEY", "") or "").strip()
    )


def verify_turnstile(token: str, remote_ip: str = "") -> bool:
    """Validate a Turnstile response token with Cloudflare's siteverify API."""
    if not turnstile_enabled():
        return True
    if not (token or "").strip():
        return False
    data = {
        "secret": (settings.TURNSTILE_SECRET_KEY or "").strip(),
        "response": token,
    }
    if remote_ip:
        data["remoteip"] = remote_ip
    verify_url = getattr(
        settings,
        "TURNSTILE_VERIFY_URL",
        "https://challenges.cloudflare.com/turnstile/v0/siteverify",
    )
    try:
        resp = requests.post(verify_url, data=data, timeout=_VERIFY_TIMEOUT_SECONDS)
        result = resp.json()
    except (requests.RequestException, ValueError) as exc:
        # Fail open: do not block legitimate users when Cloudflare is unreachable.
        logger.warning("turnstile_verify_unavailable type=%s", type(exc).__name__)
        return True
    return bool(result.get("success"))


__all__ = ["turnstile_enabled", "verify_turnstile"]
