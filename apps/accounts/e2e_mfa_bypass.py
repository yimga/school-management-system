"""Playwright / local E2E only — never active in production."""

from __future__ import annotations

import os

from django.conf import settings


def e2e_mfa_bypass_active(request) -> bool:
    """True when DEBUG + RMC_E2E_BYPASS_MFA=1 on a local or platform-dev host.

    Local Chromium e2e uses ``manager.localhost`` (Windows does not resolve
    ``*.localhost`` via DNS; MAP + Host keep control-plane routing). Treat
    ``*.localhost`` like ``127.0.0.1`` for this bypass only.
    """
    if os.environ.get("RMC_E2E_BYPASS_MFA", "").strip() != "1":
        return False
    if not getattr(settings, "DEBUG", False):
        return False
    host = (request.get_host() or "").split(":")[0].lower()
    if host in {"127.0.0.1", "localhost", "testserver"}:
        return True
    if host.endswith(".localhost"):
        return True
    return host.endswith(".runmycampus.com")
