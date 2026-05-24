#!/usr/bin/env python3
"""Preview Shell 100x Phase 5 gate — surpass layer + Playwright spec present."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(script: str) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return False, "\n".join(out.strip().splitlines()[-6:])
    return True, out.strip().splitlines()[-1] if out.strip() else "ok"


def main() -> int:
    findings: list[str] = []

    required = (
        "static/js/rmc-cp-pulse-sheet.js",
        "templates/partials/cockpit/_pulse_drill_sheet.html",
        "tests/e2e/preview-shell-parity.spec.js",
    )
    for rel in required:
        if not (ROOT / rel).is_file():
            findings.append(f"missing {rel}")

    pulse = (ROOT / "templates/partials/cockpit/_platform_pulse.html").read_text(
        encoding="utf-8", errors="replace"
    )
    if "data-rmc-cp-pulse-drill" not in pulse:
        findings.append("_platform_pulse.html: missing data-rmc-cp-pulse-drill")

    skeleton = (ROOT / "templates/control_plane_skeleton.html").read_text(
        encoding="utf-8", errors="replace"
    )
    if "rmc-cp-pulse-sheet.js" not in skeleton:
        findings.append("control_plane_skeleton.html: missing rmc-cp-pulse-sheet.js")

    css = (ROOT / "static/css/manager-cockpit-v7.css").read_text(
        encoding="utf-8", errors="replace"
    )
    if "prefers-reduced-motion" not in css or ".rmc-cockpit-pulse" not in css:
        findings.append("manager-cockpit-v7.css: reduced-motion pulse rules missing")

    if findings:
        print("verify_preview_shell_100x_phase5: FAIL (pre-flight)", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    for script in (
        "scripts/verify_preview_shell_100x_phase4.py",
        "scripts/verify_copilot_rail_contract.py",
        "scripts/audit_luxury_ui_surface.py",
    ):
        ok, detail = _run(script)
        if not ok:
            findings.append(f"{script}: {detail}")

    if findings:
        print("verify_preview_shell_100x_phase5: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_preview_shell_100x_phase5: PREVIEW_SHELL_100X_PHASE5_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
