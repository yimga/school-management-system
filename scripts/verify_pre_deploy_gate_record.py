#!/usr/bin/env python3
"""
§11.4 / RELEASE_CHECKLIST: committed pre_deploy gate log discipline.

Ensures ``docs/generated/pre_deploy_gate_run.txt`` exists, is non-trivial, and
ends with a successful gate marker. Optional ``[gate-finished] EXIT=0`` when
present (from ``record_pre_deploy_gate_output.sh``) must not show failure.

Does not run the gate — only validates the artifact developers commit after
``record_pre_deploy_gate_output.sh``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "generated" / "pre_deploy_gate_run.txt"
_MIN_BYTES = 2_000
_TAIL_LINES = 400


def main() -> int:
    errors: list[str] = []
    if not RECORD.is_file():
        errors.append(
            f"Missing {RECORD.relative_to(ROOT)} — run "
            "bash scripts/record_pre_deploy_gate_output.sh (or tee pre_deploy output) "
            "and commit the file per RELEASE_CHECKLIST.md"
        )
        return _fail(errors)

    raw = RECORD.read_bytes()
    if len(raw) < _MIN_BYTES:
        errors.append(
            f"{RECORD.relative_to(ROOT)} too small ({len(raw)} bytes < {_MIN_BYTES}); "
            "not a credible full gate log"
        )

    text = raw.decode("utf-8", errors="replace")
    tail = "\n".join(text.splitlines()[-_TAIL_LINES:])
    if "[pre_deploy_gate] PASSED" not in tail:
        errors.append(
            f"{RECORD.relative_to(ROOT)}: last {_TAIL_LINES} lines must contain "
            "'[pre_deploy_gate] PASSED' (gate did not complete successfully in this log)"
        )

    finished = re.findall(r"\[gate-finished\]\s*EXIT=(\d+)", text)
    if finished and finished[-1] != "0":
        errors.append(
            f"{RECORD.relative_to(ROOT)}: last [gate-finished] shows failure "
            f"(EXIT={finished[-1]})"
        )

    if errors:
        return _fail(errors)

    print(
        "verify_pre_deploy_gate_record: PASS "
        f"({RECORD.relative_to(ROOT)}, {len(raw)} bytes, success tail OK)"
    )
    return 0


def _fail(errors: list[str]) -> int:
    print("verify_pre_deploy_gate_record: FAIL", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
