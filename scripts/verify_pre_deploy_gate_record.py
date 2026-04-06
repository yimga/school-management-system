#!/usr/bin/env python3
"""
§11.4 / RELEASE_CHECKLIST: committed pre_deploy gate log discipline.

Ensures ``docs/generated/pre_deploy_gate_run.txt`` exists, is non-trivial, and
ends with a successful gate marker. Optional ``[gate-finished] EXIT=0`` when
present (from ``record_pre_deploy_gate_output.sh``) must not show failure.

Does not run the gate — only validates the artifact developers commit after
``record_pre_deploy_gate_output.sh``.

Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_MIN_BYTES = 2_000
_TAIL_LINES = 400


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify committed pre_deploy_gate_run.txt discipline."
    )
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root to inspect (default: this repository root).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"verify_pre_deploy_gate_record: {exc}", file=sys.stderr)
        return 1

    record = root / "docs" / "generated" / "pre_deploy_gate_run.txt"
    errors: list[str] = []
    if not record.is_file():
        errors.append(
            f"Missing {record.relative_to(root)} — run "
            "bash scripts/record_pre_deploy_gate_output.sh (or tee pre_deploy output) "
            "and commit the file per RELEASE_CHECKLIST.md"
        )
        return _fail(errors)

    raw = record.read_bytes()
    if len(raw) < _MIN_BYTES:
        errors.append(
            f"{record.relative_to(root)} too small ({len(raw)} bytes < {_MIN_BYTES}); "
            "not a credible full gate log"
        )

    text = raw.decode("utf-8", errors="replace")
    tail = "\n".join(text.splitlines()[-_TAIL_LINES:])
    if "[pre_deploy_gate] PASSED" not in tail:
        errors.append(
            f"{record.relative_to(root)}: last {_TAIL_LINES} lines must contain "
            "'[pre_deploy_gate] PASSED' (gate did not complete successfully in this log)"
        )

    finished = re.findall(r"\[gate-finished\]\s*EXIT=(\d+)", text)
    if finished and finished[-1] != "0":
        errors.append(
            f"{record.relative_to(root)}: last [gate-finished] shows failure "
            f"(EXIT={finished[-1]})"
        )

    if errors:
        return _fail(errors)

    print(
        "verify_pre_deploy_gate_record: PASS "
        f"({record.relative_to(root)}, {len(raw)} bytes, success tail OK)"
    )
    return 0


def _fail(errors: list[str]) -> int:
    print("verify_pre_deploy_gate_record: FAIL", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(None))
