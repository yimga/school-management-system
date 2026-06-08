#!/usr/bin/env python3
"""
Verify Zero-Friction OS Phase 0 audit artifacts are present, fresh, and complete.

Exit 0 when:
  - All four Phase 0 JSON artifacts exist
  - Zone manifest: all 15 zones audited
  - Shell matrix: all root + sub-router shells exist
  - Ledger: scored >= 1000 templates
  - Scanner gap report: documents all registry entries

Run: python scripts/verify_zero_friction_phase0.py [--strict]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = {
    "zone_manifest": ROOT / "docs/generated/zero_friction_zone_manifest.json",
    "audit_ledger": ROOT / "docs/generated/zero_friction_audit_ledger.json",
    "scanner_gaps": ROOT / "docs/generated/scanner_coverage_gap_report.json",
    "shell_matrix": ROOT / "docs/generated/zero_friction_shell_matrix.json",
}

MIN_TEMPLATE_ROWS = 1000
EXPECTED_ZONES = 15
EXPECTED_SCANNER_ENTRIES = 7


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Also require scanner open_gaps == 0 (after Phase 0c closure).",
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Run generate_zero_friction_phase0_audit.py --write before checks.",
    )
    args = parser.parse_args(argv)

    if args.regenerate:
        rc = subprocess.call(
            [sys.executable, str(ROOT / "scripts/generate_zero_friction_phase0_audit.py"), "--write"],
            cwd=str(ROOT),
        )
        if rc != 0:
            return rc

    errors: list[str] = []

    for name, path in ARTIFACTS.items():
        if not path.is_file():
            errors.append(f"missing artifact: {name} ({path.relative_to(ROOT).as_posix()})")

    if errors:
        for e in errors:
            print(f"verify_zero_friction_phase0: {e}", file=sys.stderr)
        return 1

    manifest = json.loads(ARTIFACTS["zone_manifest"].read_text(encoding="utf-8"))
    ledger = json.loads(ARTIFACTS["audit_ledger"].read_text(encoding="utf-8"))
    scanner = json.loads(ARTIFACTS["scanner_gaps"].read_text(encoding="utf-8"))
    shell = json.loads(ARTIFACTS["shell_matrix"].read_text(encoding="utf-8"))

    if manifest.get("zone_count") != EXPECTED_ZONES:
        errors.append(f"zone_count expected {EXPECTED_ZONES}, got {manifest.get('zone_count')}")
    if not manifest.get("zones_complete"):
        errors.append("zones_complete is false — not all audit zones enumerated")
    if manifest.get("zones_audited", 0) < EXPECTED_ZONES:
        errors.append(
            f"zones_audited {manifest.get('zones_audited')} < {EXPECTED_ZONES}"
        )

    scored = ledger.get("template_rows_scored", 0)
    if scored < MIN_TEMPLATE_ROWS:
        errors.append(f"template_rows_scored {scored} < {MIN_TEMPLATE_ROWS}")

    if len(ledger.get("top_100_routes", [])) < 100:
        errors.append("top_100_routes has fewer than 100 entries")

    if scanner.get("scanner_entries", 0) < EXPECTED_SCANNER_ENTRIES:
        errors.append(
            f"scanner_entries {scanner.get('scanner_entries')} < {EXPECTED_SCANNER_ENTRIES}"
        )

    if args.strict and scanner.get("open_gaps", 1) > 0:
        errors.append(
            f"strict mode: open_gaps={scanner.get('open_gaps')} (Phase 0c not closed)"
        )

    if not shell.get("audited"):
        missing = shell.get("missing_paths", [])
        errors.append(f"shell matrix incomplete; missing: {missing}")

    if errors:
        print("verify_zero_friction_phase0: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(
        "verify_zero_friction_phase0: PASS "
        f"(zones={manifest.get('zones_audited')}, templates={scored}, "
        f"open_gaps={scanner.get('open_gaps')}, shells_ok={shell.get('audited')})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
