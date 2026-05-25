#!/usr/bin/env python3
"""Bundle verifier for CP v8 closeout: layout assets, MFA flow, dropdowns, spacing."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()


def main() -> int:
    checks: list[tuple[str, list[str]]] = [
        ("header_dropdown_viewport", ["python", "scripts/verify_header_dropdown_viewport.py"]),
        ("dead_hrefs_strict", ["python", "scripts/scan_operator_shell_dead_hrefs.py", "--strict"]),
        ("surface_spacing", ["python", "scripts/audit_surface_spacing_contract.py", "--json"]),
        ("interaction_integrity", ["python", "scripts/verify_interaction_integrity_completion.py"]),
        ("template_render_safety", ["python", "scripts/audit_template_render_safety.py"]),
        ("split_hero_action_rows", ["python", "scripts/audit_split_hero_action_rows.py"]),
        ("admin_steering_strip", ["python", "scripts/verify_admin_steering_strip_contract.py"]),
        (
            "surface_preview_interactivity",
            ["python", "scripts/verify_surface_preview_interactivity.py"],
        ),
    ]
    assets = [
        "static/css/rmc-cp-v8-layout-contract.css",
        "static/css/rmc-cp-v8-full-width.css",
        "static/css/rmc-dropdown-viewport-safe.css",
        "static/js/rmc-dropdown-viewport-safe.js",
        "apps/accounts/mfa_setup_flow.py",
        "templates/accounts/partials/_mfa_setup_wizard_inline.html",
        "templates/accounts/partials/_profile_security_hub.html",
        "templates/components/user_dropdown.html",
        "templates/components/rmc_operator_workspace_dropdown.html",
    ]
    missing = [a for a in assets if not (ROOT / a).is_file()]
    if missing:
        print("verify_cp_v8_operator_closeout: FAIL missing assets", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 1

    failed = []
    for name, cmd in checks:
        code, out = _run(cmd)
        if code != 0:
            failed.append((name, out[-500:]))
            continue
        if name == "surface_spacing" and '"finding_count": 0' not in out and '"finding_count":0' not in out:
            if '"finding_count":' in out and '"finding_count": 0' not in out.replace(" ", ""):
                failed.append((name, "spacing findings > 0"))
        if name == "dead_hrefs_strict" and "0 finding" not in out:
            failed.append((name, out[-300:]))
        if name == "interaction_integrity" and "INTERACTION_INTEGRITY_PASS" not in out:
            failed.append((name, out[-300:]))
        if name == "template_render_safety" and "Total findings: 0" not in out:
            failed.append((name, out[-300:]))
        if name == "split_hero_action_rows" and "0 findings" not in out:
            failed.append((name, out[-300:]))
        if name == "admin_steering_strip" and "OK" not in out and "PASS" not in out:
            failed.append((name, out[-300:]))
        if name == "surface_preview_interactivity" and "OK" not in out:
            failed.append((name, out[-300:]))

    if failed:
        print("verify_cp_v8_operator_closeout: FAIL", file=sys.stderr)
        for name, snippet in failed:
            print(f"  [{name}] {snippet}", file=sys.stderr)
        return 1

    print("verify_cp_v8_operator_closeout: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
