"""
v2.79 — boot-time advisory checks.

`OAUTH_CALLBACK_BASE_URL` is the absolute base URL we paste into upstream
OAuth marketplaces (Zoom App Marketplace, Google Cloud Console, Microsoft
Entra, Slack Apps). When it's unset:

  - dev: harmless — `oauth._absolute_callback_url` falls back to
    `request.get_host()` which is whatever the dev browser hit.
  - prod: probably broken — the upstream redirect URI registered in the
    console must match exactly. Falling back to `request.get_host()` only
    works if EVERY user hits the same hostname *and* uses HTTPS *and* the
    proxy headers are forwarded correctly. For most real deploys, set
    it explicitly.

This module emits a logger.warning() at boot when the setting is missing in
a production-looking environment (DEBUG=False) so operators see it in the
worker / web container logs immediately instead of finding out 4 hours
later when the first OAuth dance fails.

It is an *advisory* — never raises. The redirect_uri_registry page also
surfaces the same state visually for the platform owner.
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def _effective_oauth_callback_base_url() -> str:
    """Resolved callback base (settings default + manager fallback)."""
    raw = str(getattr(settings, "OAUTH_CALLBACK_BASE_URL", "") or "").strip()
    if raw:
        return raw
    if not bool(getattr(settings, "DEBUG", False)):
        manager = str(getattr(settings, "MANAGER_PLATFORM_BASE_URL", "") or "").strip()
        if manager:
            return manager
    return ""


def oauth_callback_base_url_state() -> dict:
    """Inspect the OAUTH_CALLBACK_BASE_URL setting; return a structured
    diagnostic the redirect-URI registry page and the boot-warning share.
    """
    raw = _effective_oauth_callback_base_url()
    debug = bool(getattr(settings, "DEBUG", False))
    if not raw:
        return {
            "configured": False,
            "value": "",
            "level": "info" if debug else "warning",
            "summary": (
                "OAUTH_CALLBACK_BASE_URL is not set. OAuth callbacks will "
                "use the request's host header, which is fine for dev but "
                "will fail in prod if upstreams (Zoom / Google / Microsoft) "
                "have a fixed redirect URI registered."
            ),
            "env_var_hint": "OAUTH_CALLBACK_BASE_URL=https://app.runmycampus.com",
        }
    if not raw.startswith(("http://", "https://")):
        return {
            "configured": True,
            "value": raw,
            "level": "warning",
            "summary": (
                f"OAUTH_CALLBACK_BASE_URL={raw!r} does not start with http:// "
                "or https://. Upstreams will reject this redirect URI."
            ),
            "env_var_hint": "OAUTH_CALLBACK_BASE_URL=https://app.runmycampus.com",
        }
    if not debug and raw.startswith("http://"):
        return {
            "configured": True,
            "value": raw,
            "level": "warning",
            "summary": (
                f"OAUTH_CALLBACK_BASE_URL={raw!r} is plain http:// in a "
                "non-DEBUG environment. Most upstream OAuth providers "
                "(Google, Microsoft, Zoom) refuse non-https redirect URIs."
            ),
            "env_var_hint": "OAUTH_CALLBACK_BASE_URL=https://app.runmycampus.com",
        }
    return {
        "configured": True,
        "value": raw,
        "level": "ok",
        "summary": "OAUTH_CALLBACK_BASE_URL is set and well-formed.",
        "env_var_hint": "",
    }


def warn_if_oauth_callback_base_url_missing() -> None:
    """Boot-time advisory; called from `IntegrationsMarketplaceConfig.ready()`.
    Never raises. Emits at WARNING level when something is off in a
    production-looking environment; at INFO in DEBUG.
    """
    try:
        state = oauth_callback_base_url_state()
    except Exception:  # noqa: BLE001 — boot advisory must never break startup
        logger.exception(
            "integrations_marketplace: oauth_callback_base_url_state crashed"
        )
        return
    level = state.get("level", "ok")
    msg = "integrations_marketplace: " + str(state.get("summary", ""))
    if level == "ok":
        return
    if level == "warning":
        logger.warning(msg)
        return
    logger.info(msg)


__all__ = ["oauth_callback_base_url_state", "warn_if_oauth_callback_base_url_missing"]
