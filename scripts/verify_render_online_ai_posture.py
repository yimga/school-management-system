#!/usr/bin/env python3
"""Verify Render online SaaS AI posture (cloud-first gateway + AI Center copy)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []

    posture = ROOT / "services/ai_deployment_posture.py"
    if not posture.is_file():
        errors.append(f"missing {posture}")
    else:
        text = posture.read_text(encoding="utf-8")
        for needle in (
            "default_tier_chain_for_profile",
            "merge_effective_task_tiers",
            "probe_litellm_reachable",
            "build_posture_fields",
            "enrich_public_provider_status",
        ):
            if needle not in text:
                errors.append(f"ai_deployment_posture missing {needle}")

    gw = ROOT / "services/ai_gateway.py"
    if "ai_deployment_posture" not in gw.read_text(encoding="utf-8"):
        errors.append("ai_gateway._task_tiers must import ai_deployment_posture")

    provider = ROOT / "apps/portal/ai_provider.py"
    pt = provider.read_text(encoding="utf-8")
    if "probe_litellm_reachable" not in pt:
        errors.append("ai_provider.probe must try litellm on online/hybrid")

    ai_center = ROOT / "templates/siteconfig/partials/ai_center_body.html"
    html = ai_center.read_text(encoding="utf-8")
    for needle in (
        "posture_label",
        "gateway_tier_chain",
        "LITELLM_PROXY_URL",
        "show_operator_ai_setup",
        "deployment_profile",
    ):
        if needle not in html:
            errors.append(f"ai_center_body missing {needle}")

    health_js = ROOT / "static/js/rmc-ai-health-pill.js"
    if "litellm" not in health_js.read_text(encoding="utf-8"):
        errors.append("rmc-ai-health-pill.js missing litellm handling")

    posture_doc = ROOT / "docs/AI_DEPLOYMENT_POSTURE.md"
    if not posture_doc.is_file():
        errors.append(f"missing {posture_doc}")
    elif "LITELLM_PROXY_URL" not in posture_doc.read_text(encoding="utf-8"):
        errors.append("AI_DEPLOYMENT_POSTURE.md missing Render LITELLM section")
    elif "gpt-5.4-mini" not in posture_doc.read_text(encoding="utf-8"):
        errors.append("AI_DEPLOYMENT_POSTURE.md missing Option A default model gpt-5.4-mini")

    operator_doc = ROOT / "docs/OPERATOR_OLLAMA_AND_RENDER.md"
    if not operator_doc.is_file():
        errors.append(f"missing {operator_doc}")
    elif "AI_DEPLOYMENT_POSTURE" not in operator_doc.read_text(encoding="utf-8"):
        errors.append("OPERATOR_OLLAMA_AND_RENDER.md must reference AI_DEPLOYMENT_POSTURE")

    if errors:
        for err in errors:
            print(f"FAIL: {err}")
        return 1
    print("RENDER_ONLINE_AI_POSTURE_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
