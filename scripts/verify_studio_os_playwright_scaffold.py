#!/usr/bin/env python3
"""Wave 6: Studio OS manager UX Playwright spec exists and documents manager host."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "tests/e2e/studio-os-manager-ux.spec.js"


def main() -> int:
    findings: list[str] = []
    if not SPEC.is_file():
        findings.append("missing tests/e2e/studio-os-manager-ux.spec.js")
    else:
        text = SPEC.read_text(encoding="utf-8", errors="replace")
        for needle in (
            "data-rmc-studio-focus",
            "data-rmc-studio-workspace",
            "data-rmc-studio-inline-control",
            "data-rmc-studio-embed",
            "AUTH_STATE_PATH",
            "data-studio-command-deck",
            "data-studio-operator-toolbar",
        ):
            if needle not in text:
                findings.append(f"studio-os-manager-ux.spec.js missing {needle!r}")
    if findings:
        print(f"verify_studio_os_playwright_scaffold: {len(findings)} finding(s)\n")
        for item in findings:
            print(f"  - {item}")
        return 1
    print("verify_studio_os_playwright_scaffold: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
