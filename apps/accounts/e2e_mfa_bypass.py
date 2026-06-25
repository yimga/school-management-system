"""Playwright / local E2E only — never active in production."""

from __future__ import annotations

import os

from django.conf import settings


def e2e_mfa_bypass_active(request) -> bool:
    """True when DEBUG + RMC_E2E_BYPASS_MFA=1 on a local or *.runmycampus.com host."""
    if os.environ.get("RMC_E2E_BYPASS_MFA", "").strip() != "1":
        return False
    if not getattr(settings, "DEBUG", False):
        return False
    host = (request.get_host() or "").split(":")[0].lower()
    return host in {"127.0.0.1", "localhost", "testserver"} or host.endswith(
        ".runmycampus.com"
    )
