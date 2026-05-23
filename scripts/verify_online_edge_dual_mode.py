#!/usr/bin/env python3
"""Verify online + edge dual-mode contracts (offline bundle, docs, gateway hooks)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []

    bundle = ROOT / "apps/platform_runtime/offline_mode_bundle.py"
    if not bundle.is_file():
        errors.append(f"missing {bundle}")
    else:
        text = bundle.read_text(encoding="utf-8")
        for needle in (
            "enable_offline_mode",
            "_enable_offline_mode_policy_module",
            "apply_offline_mode_bundle_for_school",
            "maybe_apply_offline_bundle_on_provision",
            '("hybrid", "edge")',
        ):
            if needle not in text:
                errors.append(f"offline_mode_bundle missing {needle}")

    cmd = ROOT / "apps/platform_runtime/management/commands/apply_offline_mode_bundle.py"
    if not cmd.is_file():
        errors.append(f"missing {cmd}")

    hub_doc = ROOT / "docs/LOCAL_HUB_MODE.md"
    if not hub_doc.is_file():
        errors.append(f"missing {hub_doc}")
    elif "Online (SaaS)" not in hub_doc.read_text(encoding="utf-8"):
        errors.append("LOCAL_HUB_MODE.md missing Online (SaaS) section")

    gw = ROOT / "services/ai_gateway.py"
    gw_text = gw.read_text(encoding="utf-8")
    if "litellm_api_key" not in gw_text and "LITELLM_API_KEY" not in gw_text:
        errors.append("ai_gateway._call_litellm missing litellm API key wiring")

    portal = ROOT / "templates/portal_base.html"
    portal_text = portal.read_text(encoding="utf-8")
    if "deploymentProfile" not in portal_text:
        errors.append("portal_base SMS_OFFLINE_CONFIG missing deploymentProfile")
    if "maxQueueItems" not in portal_text:
        errors.append("portal_base SMS_OFFLINE_CONFIG missing maxQueueItems")
    if "meshEnabled" not in portal_text:
        errors.append("portal_base SMS_OFFLINE_CONFIG missing meshEnabled")

    hub_doc_text = hub_doc.read_text(encoding="utf-8")
    if "mDNS" not in hub_doc_text and "_runmycampus-hub._tcp.local." not in hub_doc_text:
        errors.append("LOCAL_HUB_MODE.md missing mDNS hub service type")

    settings = ROOT / "config/settings.py"
    st = settings.read_text(encoding="utf-8")
    for key in ("RMC_DEPLOYMENT_PROFILE", "RMC_AUTO_APPLY_OFFLINE_BUNDLE_ON_PROVISION"):
        if key not in st:
            errors.append(f"settings missing {key}")

    posture = ROOT / "services/ai_deployment_posture.py"
    if not posture.is_file():
        errors.append(f"missing {posture}")

    if errors:
        for err in errors:
            print(f"FAIL: {err}")
        return 1
    print("ONLINE_EDGE_DUAL_MODE_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
