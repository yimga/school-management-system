#!/usr/bin/env python3
"""
Phase 12 Sweep A/B/C: run no-hardcoding and tenant-settings linters.
Sweep = constants (A), forms (B), conditionals (C) that should use policy/registry instead of hardcoding.
Exits 0 only if both scripts report no hits. Use in CI or pre-push.
Usage: python scripts/run_sweep_ab.py [--exit-zero]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="Run Sweep A/B/C linters (check_no_hardcoding + lint_tenant_settings).")
    ap.add_argument("--exit-zero", action="store_true", help="Always exit 0 (report only).")
    args = ap.parse_args()
    root = Path(__file__).resolve().parent.parent
    scripts = [
        (root / "scripts" / "check_no_hardcoding.py", "No-hardcoding (country/region/tenant literals)"),
        (root / "scripts" / "lint_tenant_settings.py", "Tenant settings (SiteSettings.get_solo, DEFAULT_*)"),
    ]
    failed = []
    for script, label in scripts:
        if not script.is_file():
            print(f"Skip {label}: {script} not found", file=sys.stderr)
            continue
        r = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=root,
            capture_output=True,
            text=True,
        )
        print(f"--- {label} ---")
        print(r.stdout or "")
        if r.stderr:
            print(r.stderr, file=sys.stderr)
        if r.returncode != 0:
            failed.append(label)
    if failed:
        print(f"\nSweep A/B/C: {len(failed)} linter(s) reported hits: {', '.join(failed)}.")
        return 0 if args.exit_zero else 1
    print("\nSweep A/B/C: no hits.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
