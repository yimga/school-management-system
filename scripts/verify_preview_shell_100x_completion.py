#!/usr/bin/env python3
"""Preview Shell 100x Parity — program completion gate (batch 1483).

Runs existing shell parity verifiers plus tenant v3 gate. Fails until all
implementation phases 1478–1483 are marked DONE in SOT and mechanical
checks pass.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PHASE_BATCHES = tuple(range(1478, 1484))

REQUIRED_SCRIPTS = (
    "scripts/verify_all_preview_shell_html_implementation.py",
    "scripts/verify_platform_shell_preview_parity.py",
    "scripts/verify_preview_shell_100x_tenant_parity.py",
    "scripts/verify_preview_shell_100x_phase4.py",
    "scripts/verify_preview_shell_100x_phase5.py",
    "scripts/verify_copilot_rail_contract.py",
)

PHASE5_ARTIFACTS = (
    "tests/e2e/preview-shell-parity.spec.js",
    "static/js/rmc-cp-pulse-sheet.js",
)


def _text(rel: str) -> str:
    path = ROOT / rel
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def _sot_phase_done(batch: int) -> bool:
    sot = _text("docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md")
    pattern = rf"batch {batch}[^:]*:\*\* \*\*DONE"
    if re.search(pattern, sot, re.IGNORECASE):
        return True
    # Alternate: **DONE (Lane 1)
    pattern2 = rf"batch {batch}.*\*\*DONE"
    return bool(re.search(pattern2, sot, re.IGNORECASE | re.DOTALL))


def _run(script_rel: str) -> tuple[bool, str]:
    path = ROOT / script_rel
    if not path.is_file():
        return False, f"missing {script_rel}"
    proc = subprocess.run(
        [sys.executable, str(path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=600,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        tail = "\n".join(out.strip().splitlines()[-8:])
        return False, f"{script_rel} exit {proc.returncode}\n{tail}"
    return True, out.strip().splitlines()[-1] if out.strip() else "ok"


def main() -> int:
    findings: list[str] = []

    for batch in PHASE_BATCHES:
        if not _sot_phase_done(batch):
            findings.append(f"SOT batch {batch} not DONE — complete phase before program gate")

    for rel in REQUIRED_SCRIPTS:
        if not (ROOT / rel).is_file():
            findings.append(f"missing {rel}")

    for rel in PHASE5_ARTIFACTS:
        if not (ROOT / rel).is_file():
            findings.append(f"missing phase5 artifact {rel}")

    archetypes = ROOT / "templates/archetypes"
    for name in ("cp_operator_dashboard.html", "cp_admin_backoffice.html", "tp_role_home.html"):
        if not (archetypes / name).is_file():
            findings.append(f"missing templates/archetypes/{name}")

    if findings:
        print("verify_preview_shell_100x_completion: FAIL (pre-flight)", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    for script in REQUIRED_SCRIPTS:
        ok, detail = _run(script)
        if not ok:
            findings.append(detail)

    if findings:
        print("verify_preview_shell_100x_completion: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_preview_shell_100x_completion: PREVIEW_SHELL_100X_PARITY_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
