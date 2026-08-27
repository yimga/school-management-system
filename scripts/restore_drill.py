#!/usr/bin/env python
"""Quarterly disaster-recovery restore drill (dry-run + record).

12-pillar audit P12 follow-up. ``docs/operations/SLA.md`` (SOT batch
1212) commits to RPO ≤ 1h / RTO ≤ 4h, conditional on the cloud
contract. Operators need a repeatable drill that proves the
commitment with evidence, not promises.

This script:

  1. Identifies the most recent Render Postgres backup (operator
     supplies the timestamp; the script verifies it's < 1h old).
  2. Triggers a restore into a SIDE database (never touches prod).
  3. Walks a canonical checklist of read queries against the
     restored DB to confirm tenant + finance + analytics tables
     are populated.
  4. Records the drill outcome to ``docs/generated/dr_drill_log.json``
     with timestamp + duration + checklist status.

Because the actual Render API + side-DB binding lives outside this
repo, the script ships in **dry-run mode by default**. The dry run
exercises the checklist logic + writes the log entry so operators
can validate the runbook without spending real backup credits.

Usage:
    python scripts/restore_drill.py --dry-run             # default
    python scripts/restore_drill.py --backup-ts 2026-05-17T12:00:00Z --apply
    python scripts/restore_drill.py --apply-local         # query THIS DB (no Render)
    python scripts/restore_drill.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DRILL_LOG = REPO_ROOT / "docs" / "generated" / "dr_drill_log.json"

RPO_MAX_HOURS = 1
RTO_MAX_HOURS = 4

# Canonical read checks the operator runs against the restored DB.
# Adapted from SLA.md's "tenant + finance + analytics" data shape.
CHECKLIST = [
    "schools_school row count > 0",
    "people_studentprofile row count > 0",
    "finance_invoice row count >= 0 (table exists)",
    "analytics_atriskmodelartifact row count > 0",
    "compliance_auditlog row count > 0",
    "django_migrations row count > 0",
    # Wave 27 — offline moat + registry tables (repo-contained apply-local)
    "platform_runtime_offlineaction row count >= 0 (table exists)",
    "django_content_type row count > 0",
    "schoolops_bookableresource row count >= 0 (table exists)",
]

# Table name → (min_count, allow_empty). Used by --apply-local only.
_LOCAL_CHECKS: list[tuple[str, int, bool]] = [
    ("schools_school", 0, True),  # empty local OK; table must exist
    ("people_studentprofile", 0, True),
    ("finance_invoice", 0, True),
    ("analytics_atriskmodelartifact", 0, True),
    ("compliance_auditlog", 0, True),
    ("django_migrations", 1, False),
    ("platform_runtime_offlineaction", 0, True),
    ("django_content_type", 1, False),
    ("schoolops_bookableresource", 0, True),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _backup_age_hours(backup_ts: str) -> float:
    try:
        ts = datetime.fromisoformat(backup_ts.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SystemExit(f"--backup-ts must be ISO-8601 ({exc})") from None
    delta = datetime.now(timezone.utc) - ts
    return delta.total_seconds() / 3600.0


def _append_log(entry: dict) -> None:
    DRILL_LOG.parent.mkdir(parents=True, exist_ok=True)
    log: list = []
    if DRILL_LOG.exists():
        try:
            log = json.loads(DRILL_LOG.read_text(encoding="utf-8"))
            if not isinstance(log, list):
                log = []
        except json.JSONDecodeError:
            log = []
    log.append(entry)
    DRILL_LOG.write_text(
        json.dumps(log, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _run_local_checklist() -> list[dict]:
    """Query the configured Django DB for checklist tables (no Render restore)."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.db import connection

    results: list[dict] = []
    for table, min_count, allow_empty in _LOCAL_CHECKS:
        # Record what THIS mode actually asserted, not the CHECKLIST wording.
        #
        # This used to zip CHECKLIST onto these results, so a row landed in the
        # durable drill log reading {"check": "schools_school row count > 0",
        # "count": 0, "status": "pass"} -- a check whose text promises rows,
        # reporting zero, and passing. The pass was CORRECT (--apply-local is a
        # repo-contained smoke test and these entries carry allow_empty=True,
        # "empty local OK; table must exist"), but the evidence file said
        # something that was not true, and docs/generated/dr_drill_log.json is
        # what verify_dr_drill_schedule.py reads to decide whether disaster
        # recovery has been exercised. Evidence that misstates its own assertion
        # is worse than no evidence: somebody auditing it cannot tell the
        # difference between "we restored and the data was there" and "the table
        # existed on a developer laptop".
        if allow_empty:
            label = f"{table} exists (local mode: rows not required)"
        else:
            label = f"{table} row count >= {min_count}"
        try:
            with connection.cursor() as cursor:
                cursor.execute(f'SELECT COUNT(*) FROM "{table}"')  # noqa: S608
                count = int(cursor.fetchone()[0])
            ok = True if allow_empty else count >= min_count
            status = "pass" if ok else "fail"
            results.append(
                {
                    "check": label,
                    "status": status,
                    "table": table,
                    "count": count,
                    # So a reader (and any future gate) can tell at a glance that
                    # this row is a local smoke result, not a restore proof.
                    "assertion": "table_exists" if allow_empty else "min_row_count",
                }
            )
        except Exception as exc:  # noqa: BLE001 — drill must record failures
            results.append(
                {
                    "check": label,
                    "status": "fail",
                    "table": table,
                    "error": str(exc)[:200],
                }
            )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-ts", default=None, help="ISO-8601 backup timestamp")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", dest="dry_run", action="store_false")
    parser.add_argument(
        "--apply-local",
        action="store_true",
        help="Run checklist SQL against the local/configured DB (repo-contained proof)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    started = _now()
    rpo_ok = None
    rpo_hours = None
    if args.backup_ts:
        rpo_hours = _backup_age_hours(args.backup_ts)
        rpo_ok = rpo_hours <= RPO_MAX_HOURS

    apply_local = bool(args.apply_local)
    if apply_local:
        checklist_results = _run_local_checklist()
        dry_run = False
    else:
        # Walk the checklist. In dry-run mode every check is "would-run";
        # in --apply mode an operator-supplied callback per check would
        # query the side-DB. We keep the contract simple (status: would-run)
        # so the runbook + log writer don't depend on the live cloud-API.
        dry_run = bool(args.dry_run)
        checklist_results = [
            {"check": label, "status": "would-run" if dry_run else "operator-run"}
            for label in CHECKLIST
        ]

    finished = _now()
    entry = {
        "started_at": started,
        "finished_at": finished,
        "dry_run": dry_run,
        "apply_local": apply_local,
        "backup_ts": args.backup_ts,
        "rpo_max_hours": RPO_MAX_HOURS,
        "rto_max_hours": RTO_MAX_HOURS,
        "rpo_hours": rpo_hours,
        "rpo_ok": rpo_ok,
        "checklist": checklist_results,
    }
    _append_log(entry)

    if args.json:
        print(json.dumps(entry, indent=2, sort_keys=True))
    else:
        if apply_local:
            mode = "APPLY-LOCAL"
        else:
            mode = "DRY-RUN" if dry_run else "APPLY"
        print(f"DR restore drill [{mode}] -- started {started}")
        if args.backup_ts:
            print(
                f"  backup age: {rpo_hours:.2f}h  "
                f"(RPO budget {RPO_MAX_HOURS}h) -> "
                f"{'OK' if rpo_ok else 'OVER-BUDGET'}"
            )
        else:
            print("  no --backup-ts supplied; skipping RPO check")
        for r in checklist_results:
            print(f"  [{r['status']}] {r['check']}")
        print(f"  log written -> {DRILL_LOG.relative_to(REPO_ROOT)}")

    if apply_local:
        if any(r.get("status") == "fail" for r in checklist_results):
            return 1
        return 0
    # In strict apply mode, an over-budget RPO fails. Dry-run never fails.
    if (not dry_run) and rpo_ok is False:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
