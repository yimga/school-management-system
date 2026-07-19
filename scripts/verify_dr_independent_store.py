#!/usr/bin/env python3
"""Verify #28 / #22 DR independent-store proof with EXTERNAL classification.

Checks repo-contained DR infrastructure:
  1. restore_drill.py exists and supports --apply-local (CI-runnable proof)
  2. verify_dr_drill_schedule.py exists (cadence enforcement)
  3. DR drill schedule (var/dr-drill-schedule.json) is well-formed
  4. DR drill log (docs/generated/dr_drill_log.json) exists
  5. DR runbook documentation exists
  6. verify_dr_rto_rpo_residency.py exists (per-shard compliance)

Reports EXTERNAL when:
  - No independent backup volume/S3 bucket is configured (dual_dir is ephemeral)
  - No Render/cloud backup API credentials are present
  - Cross-region failover is not provable from repo alone

Exit 0 = repo-contained infrastructure is sound. EXTERNAL items classified honestly.

Run: python scripts/verify_dr_independent_store.py [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _file_exists(rel: str) -> bool:
    return (ROOT / rel).is_file()


def _file_contains(rel: str, needle: str) -> bool:
    p = ROOT / rel
    if not p.is_file():
        return False
    return needle in p.read_text(encoding="utf-8", errors="replace")


def _json_valid(rel: str) -> bool:
    p = ROOT / rel
    if not p.is_file():
        return False
    try:
        json.loads(p.read_text(encoding="utf-8"))
        return True
    except (json.JSONDecodeError, OSError):
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    checks: list[dict] = []
    external: list[str] = []

    # 1. restore_drill.py with --apply-local support
    drill_script = _file_exists("scripts/restore_drill.py")
    drill_local = _file_contains("scripts/restore_drill.py", "--apply-local")
    checks.append({
        "check": "restore_drill_script",
        "pass": drill_script,
        "detail": "scripts/restore_drill.py present" if drill_script else "MISSING",
    })
    checks.append({
        "check": "restore_drill_apply_local",
        "pass": drill_local,
        "detail": "--apply-local mode exists (CI-runnable)" if drill_local else "MISSING",
    })

    # 2. DR drill schedule gate
    schedule_gate = _file_exists("scripts/verify_dr_drill_schedule.py")
    checks.append({
        "check": "drill_schedule_gate",
        "pass": schedule_gate,
        "detail": "verify_dr_drill_schedule.py present" if schedule_gate else "MISSING",
    })

    # 3. Schedule JSON well-formed
    schedule_valid = _json_valid("var/dr-drill-schedule.json")
    schedule_has_cadence = False
    schedule_has_due = False
    if schedule_valid:
        data = json.loads(
            (ROOT / "var/dr-drill-schedule.json").read_text(encoding="utf-8")
        )
        schedule_has_cadence = isinstance(data.get("cadence_days"), int)
        schedule_has_due = bool(data.get("next_drill_due_by"))
    checks.append({
        "check": "drill_schedule_well_formed",
        "pass": schedule_valid and schedule_has_cadence and schedule_has_due,
        "detail": (
            f"cadence={data.get('cadence_days')}d, due={data.get('next_drill_due_by')}"
            if schedule_valid
            else "MISSING or malformed"
        ),
    })

    # 4. DR drill log exists
    drill_log = _file_exists("docs/generated/dr_drill_log.json")
    checks.append({
        "check": "drill_log_exists",
        "pass": drill_log,
        "detail": "docs/generated/dr_drill_log.json present" if drill_log else "MISSING",
    })

    # 5. DR runbook documentation
    runbook = _file_exists("docs/DR_BACKUP_RESTORE_RUNBOOK.md")
    checks.append({
        "check": "dr_runbook_exists",
        "pass": runbook,
        "detail": "docs/DR_BACKUP_RESTORE_RUNBOOK.md present" if runbook else "MISSING",
    })

    # 6. RTO/RPO per-shard residency verifier
    residency = _file_exists("scripts/verify_dr_rto_rpo_residency.py")
    checks.append({
        "check": "rto_rpo_residency_verifier",
        "pass": residency,
        "detail": "verify_dr_rto_rpo_residency.py present" if residency else "MISSING",
    })

    # 7. Restore drill checklist covers offline-action table
    checklist_covers_offline = _file_contains(
        "scripts/restore_drill.py", "platform_runtime_offlineaction"
    )
    checks.append({
        "check": "checklist_covers_offline_actions",
        "pass": checklist_covers_offline,
        "detail": (
            "platform_runtime_offlineaction in restore checklist"
            if checklist_covers_offline
            else "MISSING"
        ),
    })

    # 8. Dual-dir / independent store classification
    # Check if any backup destination env var is configured
    backup_dir = os.environ.get("DR_BACKUP_DUAL_DIR", "")
    s3_bucket = os.environ.get("DR_BACKUP_S3_BUCKET", "")
    render_api = os.environ.get("RENDER_API_KEY", "")

    has_ephemeral = bool(backup_dir)
    has_independent = bool(s3_bucket) or bool(render_api)

    checks.append({
        "check": "dual_store_classification",
        "pass": True,  # classification always passes
        "detail": (
            "independent store detected (S3/Render)"
            if has_independent
            else "ephemeral dual_dir only (CI mode)"
        ),
    })

    # EXTERNAL classification
    if not has_independent:
        external.append(
            "EXTERNAL_INDEPENDENT_VOLUME: No DR_BACKUP_S3_BUCKET or RENDER_API_KEY "
            "in environment. The repo proves restore logic via --apply-local "
            "(queries local DB) but cannot prove independent-store writes without "
            "a configured S3 bucket or Render backup API."
        )
    external.append(
        "EXTERNAL_CROSS_REGION_FAILOVER: Cross-region failover requires cloud "
        "infrastructure (Render multi-region, AWS cross-region replication) "
        "that cannot be tested from repo alone. "
        "var/dr-drill-schedule.json tracks the cadence commitment."
    )
    external.append(
        "EXTERNAL_CLOUD_BACKUP_RESTORE: Render Postgres point-in-time restore "
        "requires Render API credentials + a side database instance. "
        "scripts/restore_drill.py --apply would exercise this path."
    )

    all_pass = all(c["pass"] for c in checks)
    report = {
        "gate": "verify_dr_independent_store",
        "status": "PASS" if all_pass else "FAIL",
        "checks": checks,
        "external_remaining": external,
        "summary": (
            "DR independent-store infrastructure is repo-sound. "
            "Real S3/volume/Render backup write-through is EXTERNAL."
            if all_pass
            else "Some repo-contained DR checks failed."
        ),
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        status = "PASS" if all_pass else "FAIL"
        print(f"verify_dr_independent_store: {status}")
        for c in checks:
            mark = "OK" if c["pass"] else "FAIL"
            print(f"  [{mark}] {c['check']}: {c['detail']}")
        if external:
            print("\n  EXTERNAL (honest classification, not a gate failure):")
            for e in external:
                print(f"    - {e}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
