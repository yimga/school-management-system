#!/usr/bin/env python3
"""SODP Capacitor Android shell scaffold gate."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    findings: list[str] = []
    for rel in (
        "companion-capacitor/capacitor.config.json",
        "companion-capacitor/package.json",
        "companion-capacitor/README.md",
    ):
        if not (ROOT / rel).is_file():
            findings.append(f"missing {rel}")
    cfg = (ROOT / "companion-capacitor/capacitor.config.json").read_text(encoding="utf-8", errors="replace")
    if "webDir" not in cfg:
        findings.append("capacitor.config.json missing webDir")
    if findings:
        print("verify_capacitor_shell_scaffold: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("verify_capacitor_shell_scaffold: CAPACITOR_SHELL_SCAFFOLD_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
