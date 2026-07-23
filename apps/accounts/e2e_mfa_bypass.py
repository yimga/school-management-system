"""Playwright / local E2E only — never active in production."""

from __future__ import annotations

import os

from django.conf import settings


def e2e_mfa_bypass_active(request) -> bool:
    """True when DEBUG + RMC_E2E_BYPASS_MFA=1 on a strictly-local host.

    Local Chromium e2e uses ``manager.localhost`` (Windows does not resolve
    ``*.localhost`` via DNS; MAP + Host keep control-plane routing). Treat
    ``*.localhost`` like ``127.0.0.1`` for this bypass only.

    The host allow-list is deliberately limited to loopback / ``*.localhost`` /
    ``testserver`` — hostnames that can never be production. The real product
    domain (``*.runmycampus.com``) is intentionally NOT allow-listed: even
    behind ``DEBUG`` + the env flag, a single misconfigured dev/preview box on
    a ``*.runmycampus.com`` host would otherwise disable MFA platform-wide. A
    genuine cloud e2e target must use a dedicated non-production hostname.
    """
    if os.environ.get("RMC_E2E_BYPASS_MFA", "").strip() != "1":
        return False
    if not getattr(settings, "DEBUG", False):
        return False
    host = (request.get_host() or "").split(":")[0].lower()
    if host in {"127.0.0.1", "localhost", "testserver"}:
        return True
    return host.endswith(".localhost")
