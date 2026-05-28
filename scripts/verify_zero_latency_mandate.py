#!/usr/bin/env python
"""Composite v4.00.0 release gate (verify:zero-latency-mandate).

Runs every scanner v4.00.0 introduced AND the foundational checks the prior
9 zero-tolerance gates rely on. Fails (exit 1) if ANY child returns non-zero.

Wire into CI:
    npm run verify:zero-latency-mandate

Surface composed:
  * scan_rls_force_coverage.py
  * scan_edge_cache_headers.py
  * scan_rest_attendance_writes.py
  * scan_viewport_class_coverage.py
  * scan_ai_full_payload_smell.py
  * (re-runs the 9 prior gates in --compare mode if their baselines exist)

This script is the single composite the operator runs before tagging v4.00.0.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"

V4_GATES: tuple[str, ...] = (
    "scan_rls_force_coverage.py",
    "scan_edge_cache_headers.py",
    "scan_rest_attendance_writes.py",
    "scan_viewport_class_coverage.py",
    "scan_ai_full_payload_smell.py",
)

PRIOR_GATES: tuple[str, ...] = (
    "scan_drf_schema_coverage.py",
    "scan_money_float.py",
    "scan_migration_model_imports.py",
    "scan_tenant_isolation_marker_quality.py",
    "scan_pii_logging_smell.py",
    "scan_print_statements.py",
    "scan_bare_except.py",
    "scan_subprocess_shell_true.py",
    "scan_companion_canonical_headers_drift.py",
)


# Some legacy scanners use --strict instead of --compare. Map them.
_COMPARE_FLAG_OVERRIDES: dict[str, str] = {
    "scan_pii_logging_smell.py": "--strict",
    "scan_companion_canonical_headers_drift.py": "--strict",
}


def _run(script: Path, compare: bool) -> tuple[int, str]:
    if not script.exists():
        return (0, f"{script.name}: not present (skipped)")
    cmd = [sys.executable, str(script)]
    if compare:
        cmd.append(_COMPARE_FLAG_OVERRIDES.get(script.name, "--compare"))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(REPO_ROOT),
        )
    except subprocess.TimeoutExpired:
        return (2, f"{script.name}: TIMEOUT")
    tail = (proc.stdout.strip().splitlines() or [""])[-1]
    label = f"{script.name}: rc={proc.returncode}  {tail[:140]}"
    return (proc.returncode, label)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-prior",
        action="store_true",
        help="Skip the 9 prior zero-tolerance gates (run only the v4.00 additions).",
    )
    parser.add_argument(
        "--write-baselines",
        action="store_true",
        help="Write baselines instead of comparing (first-pass seeding only).",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    compare = not args.write_baselines
    results: list[dict] = []
    overall = 0
    for name in V4_GATES:
        rc, label = _run(SCRIPTS_DIR / name, compare=compare)
        results.append({"gate": name, "rc": rc, "label": label})
        overall = max(overall, rc)
    if not args.no_prior:
        for name in PRIOR_GATES:
            rc, label = _run(SCRIPTS_DIR / name, compare=True)
            results.append({"gate": name, "rc": rc, "label": label})
            overall = max(overall, rc)

    if args.json:
        print(json.dumps({"overall_rc": overall, "results": results}, indent=2, sort_keys=True))
    else:
        print("=" * 78)
        print("verify_zero_latency_mandate v4.00.0")
        print("=" * 78)
        for r in results:
            marker = "OK " if r["rc"] == 0 else "FAIL"
            print(f"  [{marker}] {r['label']}")
        print("-" * 78)
        print(f"  overall_rc = {overall}")
    return overall


if __name__ == "__main__":
    sys.exit(main())
