#!/usr/bin/env python
"""DR restore drill schedule gate.

12-pillar audit P12 follow-up. ``scripts/restore_drill.py`` exists as a
dry-run scaffold + log appender; ``docs/operations/SLA.md`` commits to a
quarterly cadence. Until this verifier shipped, the cadence lived only
in the SLA doc and nothing enforced it.

Contract:

* ``var/dr-drill-schedule.json`` declares ``next_drill_due_by`` (ISO
  date) and ``cadence_days`` (e.g. 90).
* ``docs/generated/dr_drill_log.json`` is the append-only history of
  every drill ``restore_drill.py`` has logged.
* The gate **passes** when the most recent successful drill in the log
  was completed on or after ``(next_drill_due_by - cadence_days)`` —
  i.e. an in-window drill exists for the current cycle.
* The gate **fails** in ``--strict`` mode when today is past
  ``next_drill_due_by`` and no in-window drill was logged.
* Before the first ``next_drill_due_by`` date, the gate reports
  PRE-DEADLINE and passes — drill cadence is a forward commitment, not a
  retroactive claim.

Usage:
    python scripts/verify_dr_drill_schedule.py             # text
    python scripts/verify_dr_drill_schedule.py --strict    # exit 1 if overdue
    python scripts/verify_dr_drill_schedule.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEDULE_PATH = REPO_ROOT / "var" / "dr-drill-schedule.json"
LOG_PATH = REPO_ROOT / "docs" / "generated" / "dr_drill_log.json"


@dataclass(frozen=True)
class Schedule:
    cadence_days: int
    next_drill_due_by: date


def _read_schedule() -> Schedule | None:
    if not SCHEDULE_PATH.exists():
        return None
    try:
        data = json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))
        cadence = int(data["cadence_days"])
        due = date.fromisoformat(data["next_drill_due_by"])
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return None
    return Schedule(cadence_days=cadence, next_drill_due_by=due)


def _disqualifying_reason(entry: dict) -> str:
    """Why this log entry is not evidence that disaster recovery was exercised.

    Returns "" when the entry IS a real drill.

    The previous implementation counted ANY entry carrying a parseable
    ``finished_at``. Its own docstring claimed it required an ``--apply`` run or
    a dry-run with operator-recorded statuses; it checked neither, and never
    looked at ``status`` at all. Every entry in the log therefore satisfied it,
    including:

    * ``dry_run: true`` entries whose nine checks all record ``"would-run"`` --
      the literal string meaning nothing executed;
    * ``apply_local: true`` entries, which are ``restore_drill.py --apply-local``
      smoke tests that COUNT ROWS IN THE LOCAL DEVELOPMENT DATABASE. Their
      checks carry ``allow_empty=True`` ("empty local OK; table must exist"), so
      on the usual empty dev DB they assert only that the table exists. None has
      a ``backup_ts``: no backup was fetched and nothing was restored.

    So the gate that certifies quarterly DR compliance was green because someone
    had run a script on a laptop. A drill is a RESTORE: a real backup, restored,
    then queried. That is what this now requires.
    """
    if entry.get("dry_run") is True:
        return "dry-run: checks record 'would-run', nothing was restored"
    if entry.get("apply_local") is True:
        return "--apply-local: smoke test against the local DB, not a restore"
    if not entry.get("backup_ts"):
        return "no backup_ts: no backup was restored"
    checks = entry.get("checklist") or []
    if not checks:
        return "no checklist recorded"
    if any(
        isinstance(c, dict) and c.get("status") == "fail" for c in checks
    ):
        return "checklist contains a failing check"
    return ""


def _last_successful_drill_date() -> date | None:
    for candidate, _entry in _qualifying_drills():
        return candidate  # _qualifying_drills yields newest first
    return None


def _qualifying_drills() -> list[tuple[date, dict]]:
    """(date, entry) for every log entry that is a real restore drill, newest first."""
    if not LOG_PATH.exists():
        return []
    try:
        log = json.loads(LOG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(log, list):
        return []
    found: list[tuple[date, dict]] = []
    for entry in log:
        if not isinstance(entry, dict):
            continue
        finished = entry.get("finished_at")
        if not isinstance(finished, str):
            continue
        try:
            ts = datetime.fromisoformat(finished.replace("Z", "+00:00"))
        except ValueError:
            continue
        if _disqualifying_reason(entry):
            continue
        found.append((ts.astimezone(timezone.utc).date(), entry))
    return sorted(found, key=lambda pair: pair[0], reverse=True)


def _rejected_summary() -> dict[str, int]:
    """How many log entries were rejected, by reason -- so a red is explainable."""
    if not LOG_PATH.exists():
        return {}
    try:
        log = json.loads(LOG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(log, list):
        return {}
    counts: dict[str, int] = {}
    for entry in log:
        if not isinstance(entry, dict):
            continue
        reason = _disqualifying_reason(entry)
        if reason:
            counts[reason] = counts.get(reason, 0) + 1
    return counts


def _summary(today: date) -> dict:
    schedule = _read_schedule()
    last_drill = _last_successful_drill_date()
    if schedule is None:
        return {
            "today": today.isoformat(),
            "ok": False,
            "reason": "schedule-file-missing",
        }
    cycle_start = schedule.next_drill_due_by - timedelta(
        days=schedule.cadence_days
    )
    overdue = today > schedule.next_drill_due_by
    in_window_drill = (
        last_drill is not None and last_drill >= cycle_start
    )
    pre_deadline = today < cycle_start

    if pre_deadline:
        verdict = "pre-deadline"
        ok = True
    elif in_window_drill:
        verdict = "in-window-drill-recorded"
        ok = True
    elif overdue:
        verdict = "overdue"
        ok = False
    else:
        verdict = "due-window-open"
        ok = True
    return {
        "today": today.isoformat(),
        "next_drill_due_by": schedule.next_drill_due_by.isoformat(),
        "cadence_days": schedule.cadence_days,
        "cycle_start": cycle_start.isoformat(),
        "last_drill_date": last_drill.isoformat() if last_drill else None,
        "verdict": verdict,
        "ok": ok,
        # A gate that just says "overdue" invites someone to move the date. Say
        # what was in the log and why it did not count, so the operator can see
        # the difference between "we never drilled" and "we drilled and the
        # entry is malformed".
        "qualifying_drills": len(_qualifying_drills()),
        "rejected_log_entries": _rejected_summary(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when verdict is overdue.",
    )
    args = parser.parse_args()

    payload = _summary(date.today())
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        verdict = payload.get("verdict") or "n/a"
        print(f"DR drill schedule: verdict={verdict}")
        if payload.get("reason"):
            print(f"  reason: {payload['reason']}")
        else:
            print(
                f"  cycle: {payload['cycle_start']} -> {payload['next_drill_due_by']} "
                f"(cadence {payload['cadence_days']}d)"
            )
            print(f"  last drill: {payload.get('last_drill_date') or '<none>'}")

    if args.strict and not payload.get("ok"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
