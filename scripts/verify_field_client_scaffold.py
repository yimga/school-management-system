#!/usr/bin/env python3
"""SODP Tauri Field Client scaffold gate."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    findings: list[str] = []
    for rel in (
        "companion-tauri/README.md",
        "docs/FIELD_CLIENT_TAURI_OPERATOR.md",
        "companion-tauri/src-tauri/src/main.rs",
    ):
        if not (ROOT / rel).is_file():
            findings.append(f"missing {rel}")
    readme = (ROOT / "companion-tauri/README.md").read_text(encoding="utf-8", errors="replace")
    if "RMC_FIELD_CLIENT" not in readme and "field-client" not in readme.lower():
        findings.append("companion-tauri README missing field client note")
    if findings:
        print("verify_field_client_scaffold: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("verify_field_client_scaffold: FIELD_CLIENT_SCAFFOLD_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
