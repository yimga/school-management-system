#!/usr/bin/env python3
"""
Composite Zero-Friction OS reaudit gate for phases 0–8.

Phases 0–2 and 4 must be DONE (strict). Phases 3, 5–8 may be PARTIAL with
documented residuals in zero_friction_phase_completion_register.json.

Run: python scripts/verify_zero_friction_phases_0_8.py [--run-tests]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTER = ROOT / "docs/generated/zero_friction_phase_completion_register.json"

STRICT_DONE_PHASES = {0, 1, 2, 4}
SUBPROCESS_GATES = [
    ("phase0", [sys.executable, str(ROOT / "scripts/verify_zero_friction_phase0.py")]),
    (
        "journeys",
        [sys.executable, str(ROOT / "scripts/verify_zero_friction_journeys.py")],
    ),
    (
        "page_fold",
        [sys.executable, str(ROOT / "scripts/verify_page_fold_standards.py")],
    ),
    (
        "interaction",
        [
            sys.executable,
            str(ROOT / "scripts/verify_interaction_integrity_completion.py"),
        ],
    ),
    (
        "dead_hrefs",
        [
            sys.executable,
            str(ROOT / "scripts/scan_operator_shell_dead_hrefs.py"),
            "--strict",
        ],
    ),
    (
        "shell_matrix",
        [sys.executable, str(ROOT / "scripts/verify_shell_architecture_matrix.py")],
    ),
    (
        "tenant_isolation",
        [
            sys.executable,
            str(ROOT / "scripts/scan_tenant_queryset_safety.py"),
            "--compare",
        ],
    ),
    (
        "security_surface",
        [sys.executable, str(ROOT / "scripts/audit_security_surface.py")],
    ),
    (
        "ai_posture",
        [sys.executable, str(ROOT / "scripts/verify_render_online_ai_posture.py")],
    ),
    (
        "websocket_scope",
        [sys.executable, str(ROOT / "scripts/verify_websocket_tenant_scope.py")],
    ),
    (
        "middleware_order",
        [sys.executable, str(ROOT / "scripts/verify_middleware_stack_order.py")],
    ),
    (
        "sw_version",
        [
            sys.executable,
            str(ROOT / "scripts/verify_service_worker_version.py"),
            "--check-monotonic",
        ],
    ),
]


def _run_gate(name: str, cmd: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    tail = "\n".join(out.strip().splitlines()[-3:])
    return proc.returncode == 0, f"{name}: {'OK' if proc.returncode == 0 else 'FAIL'}\n{tail}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Also run apps.platform_runtime.tests.test_zero_click_protocol",
    )
    parser.add_argument(
        "--write-register",
        action="store_true",
        help="Regenerate phase completion register before checks.",
    )
    args = parser.parse_args(argv)

    if args.write_register:
        rc = subprocess.call(
            [
                sys.executable,
                str(ROOT / "scripts/generate_zero_friction_phase_completion_register.py"),
                "--write",
            ],
            cwd=str(ROOT),
        )
        if rc != 0:
            return rc

    # Always refresh register for accurate partial/done truth.
    subprocess.call(
        [
            sys.executable,
            str(ROOT / "scripts/generate_zero_friction_phase_completion_register.py"),
            "--write",
        ],
        cwd=str(ROOT),
    )

    errors: list[str] = []
    gate_log: list[str] = []

    for name, cmd in SUBPROCESS_GATES:
        ok, msg = _run_gate(name, cmd)
        gate_log.append(msg)
        if not ok:
            errors.append(f"gate failed: {name}")

    if args.run_tests:
        ok, msg = _run_gate(
            "zero_click_tests",
            [
                sys.executable,
                str(ROOT / "scripts/run_sqlite_memory_tests.py"),
                "apps.platform_runtime.tests.test_zero_click_protocol",
            ],
        )
        gate_log.append(msg)
        if not ok:
            errors.append("gate failed: zero_click_tests")

    if not REGISTER.is_file():
        errors.append("missing zero_friction_phase_completion_register.json")
    else:
        reg = json.loads(REGISTER.read_text(encoding="utf-8"))
        by_phase = {p["phase"]: p for p in reg.get("phases", [])}
        for phase_id in STRICT_DONE_PHASES:
            row = by_phase.get(phase_id)
            if not row:
                errors.append(f"register missing phase {phase_id}")
            elif row.get("status") != "DONE":
                errors.append(
                    f"phase {phase_id} must be DONE but is {row.get('status')}"
                )
        for phase_id in range(9):
            row = by_phase.get(phase_id)
            if row and row.get("status") == "NOT_DONE":
                errors.append(f"phase {phase_id} is NOT_DONE")

    if errors:
        print("verify_zero_friction_phases_0_8: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        for line in gate_log:
            print(line)
        return 1

    reg = json.loads(REGISTER.read_text(encoding="utf-8"))
    summary = reg.get("summary", {})
    print(
        "ZERO_FRICTION_PHASES_0_8_PASS "
        f"(done={summary.get('done')}, partial={summary.get('partial')}, "
        f"gates={len(SUBPROCESS_GATES)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
