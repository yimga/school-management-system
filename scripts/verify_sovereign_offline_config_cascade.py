#!/usr/bin/env python3
"""SODP offline config cascade gate."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    findings: list[str] = []
    for rel in (
        "apps/schools/offline_delivery_settings.py",
        "templates/schools/studio/infrastructure_offline.html",
        "apps/schools/views_infrastructure.py",
    ):
        if not (ROOT / rel).is_file():
            findings.append(f"missing {rel}")
    portal = (ROOT / "templates/portal_base.html").read_text(encoding="utf-8", errors="replace")
    if "rmc_sms_offline_config.html" not in portal:
        findings.append("portal_base missing rmc_sms_offline_config partial")
    offline_partial = (ROOT / "templates/partials/rmc_sms_offline_config.html").read_text(
        encoding="utf-8", errors="replace"
    )
    if "SMS_OFFLINE_CONFIG_JSON" not in offline_partial:
        findings.append("rmc_sms_offline_config missing SMS_OFFLINE_CONFIG_JSON island")
    ctx = (ROOT / "apps/siteconfig/context_processors.py").read_text(encoding="utf-8", errors="replace")
    if "build_client_offline_config" not in ctx:
        findings.append("context_processors missing build_client_offline_config")
    if "platform_surface_settings" not in ctx:
        findings.append("context_processors missing platform_surface_settings")
    psc = (ROOT / "apps/siteconfig/platform_surface_config.py").read_text(encoding="utf-8", errors="replace")
    if "hydrateEndpoints" not in psc:
        findings.append("platform_surface_config missing hydrateEndpoints builder")
    if findings:
        print("verify_sovereign_offline_config_cascade: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("verify_sovereign_offline_config_cascade: SOVEREIGN_OFFLINE_CONFIG_CASCADE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
