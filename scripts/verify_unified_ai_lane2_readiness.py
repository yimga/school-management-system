#!/usr/bin/env python3
"""Lane 2 readiness scaffold for unified AI (Phases A–C).

Exits 0 when env contract is documented and settings hooks exist.
Does not require live LiteLLM, MCP, or axe — operator enables those in deploy.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8", errors="replace")
    settings = (ROOT / "config" / "settings.py").read_text(encoding="utf-8", errors="replace")
    required_env = (
        "AI_GATEWAY_ENABLED",
        "SUPPORT_AI_AUTO_TRIAGE_ON_CREATE",
        "HELP_ZERO_RESULT_AUTO_DRAFT_KB",
        "HELP_ZERO_RESULT_AUTO_DRAFT_HITS",
        "RMC_PRODUCT_MCP_ENABLED",
        "GEOS_A11Y_E2E",
    )
    failed: list[str] = []
    for key in required_env:
        if key not in env_example:
            failed.append(f".env.example missing {key}")
    for key in (
        "SUPPORT_AI_AUTO_TRIAGE_ON_CREATE",
        "HELP_ZERO_RESULT_AUTO_DRAFT_KB",
        "RMC_PRODUCT_MCP_ENABLED",
    ):
        if key not in settings:
            failed.append(f"settings.py missing {key}")
    lane2_script = ROOT / "scripts" / "run_geos_ai_a11y_lane2.sh"
    if not lane2_script.is_file():
        failed.append("run_geos_ai_a11y_lane2.sh missing")
    for name, ok in [
        ("env-contract", len(failed) == 0),
        ("a11y-lane2-script", lane2_script.is_file()),
    ]:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        for msg in failed:
            print(f"  - {msg}")
        print("\nUNIFIED_AI_LANE2_READINESS_FAIL")
        return 1
    print("\nUNIFIED_AI_LANE2_READINESS_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
