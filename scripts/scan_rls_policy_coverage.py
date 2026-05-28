"""v4.00.13 — RLS policy coverage scanner.

Walks every `apps/*/migrations/000*_enable_rls_postgresql.py` and asserts a
matching `*_rls_policy_default_deny.py` exists in the same app directory.
Catches the regression class where an app enables RLS on its tables but
forgets the follow-up migration that attaches a default-deny policy —
the runtime audit-pass in `apps/schools/migrations/0059_v4_00_12_rls_audit_pass.py`
catches this at apply time, but this scanner catches it in PR review.

Pure-stdlib. Exits 0 when every enable_rls migration has a matching
policy migration, 1 otherwise. JSON baseline at
``var/security-audit-baseline-rls-policy-coverage.json``.

Usage:
    python scripts/scan_rls_policy_coverage.py [--strict] [--json] [--update-baseline]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-rls-policy-coverage.json"


def _walk_app_migration_dirs() -> list[Path]:
    apps_dir = REPO_ROOT / "apps"
    out: list[Path] = []
    if not apps_dir.exists():
        return out
    for entry in sorted(apps_dir.iterdir()):
        if not entry.is_dir():
            continue
        migrations = entry / "migrations"
        if migrations.is_dir():
            out.append(migrations)
    return out


def _find_findings() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for migrations_dir in _walk_app_migration_dirs():
        app = migrations_dir.parent.name
        enable_files = sorted(p.name for p in migrations_dir.glob("*enable_rls_postgresql*.py"))
        policy_files = sorted(p.name for p in migrations_dir.glob("*rls_policy_default_deny*.py"))
        if enable_files and not policy_files:
            findings.append({
                "app": app,
                "enable_file": enable_files[0],
                "missing": "rls_policy_default_deny migration",
            })
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="RLS policy coverage scanner")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on any finding (default behavior).")
    parser.add_argument("--json", action="store_true", help="Emit JSON only.")
    parser.add_argument("--update-baseline", action="store_true", help="Rewrite the baseline JSON.")
    args = parser.parse_args()

    findings = _find_findings()
    payload = {
        "finding_count": len(findings),
        "findings": findings,
        "scanner": "scan_rls_policy_coverage",
        "version": 1,
    }

    if args.update_baseline:
        os.makedirs(BASELINE_PATH.parent, exist_ok=True)
        BASELINE_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        if not args.json:
            sys.stdout.write(f"Baseline written: {BASELINE_PATH}\n")
        return 0

    if args.json:
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        sys.stdout.write("\n")
    else:
        if not findings:
            sys.stdout.write("OK: every enable_rls_postgresql migration has a matching rls_policy_default_deny.\n")
        else:
            for f in findings:
                sys.stdout.write(f"GAP: app={f['app']} {f['enable_file']} -> missing {f['missing']}\n")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
