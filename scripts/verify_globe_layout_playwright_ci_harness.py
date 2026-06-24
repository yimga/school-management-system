#!/usr/bin/env python3
"""Verify globe layout Playwright CI harness wiring (batch 1712)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    shell = ROOT / "scripts/run_globe_layout_playwright.sh"
    workflow = ROOT / ".github/workflows/globe-layout-playwright-e2e.yml"
    spec = ROOT / "tests/e2e/control-plane-layout-audit.spec.js"

    if not shell.is_file():
        errors.append("missing run_globe_layout_playwright.sh")
    elif "GLOBE_LAYOUT_PLAYWRIGHT_PASS" not in shell.read_text(encoding="utf-8"):
        errors.append("run_globe_layout_playwright.sh missing GLOBE_LAYOUT_PLAYWRIGHT_PASS token")

    if not workflow.is_file():
        errors.append("missing globe-layout-playwright-e2e.yml workflow")
    else:
        wf = workflow.read_text(encoding="utf-8")
        for needle in (
            "run_globe_layout_playwright.sh",
            "verify_globe_void_ai_lab_parity.py",
            "verify_world_globe_10x.py",
            "manager.runmycampus.com",
        ):
            if needle not in wf:
                errors.append(f"globe workflow missing {needle}")

    if not spec.is_file():
        errors.append("missing control-plane-layout-audit.spec.js")

    if errors:
        for err in errors:
            print(f"GLOBE_LAYOUT_PLAYWRIGHT_CI_HARNESS_FAIL: {err}")
        return 1

    print("GLOBE_LAYOUT_PLAYWRIGHT_CI_HARNESS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
