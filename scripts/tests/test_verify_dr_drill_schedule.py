"""What counts as a disaster-recovery drill.

WHY THIS FILE EXISTS
--------------------
``verify_dr_drill_schedule.py`` certifies that the quarterly DR commitment in
``docs/operations/SLA.md`` is being met. It was green. It was green because it
counted any log entry with a parseable ``finished_at``.

Its own docstring claimed it required an ``--apply`` run, or a dry-run with
operator-recorded checklist statuses. It checked neither, and never read
``status`` at all. So all 32 entries in ``docs/generated/dr_drill_log.json``
qualified, and not one of them was a restore:

* 19 were ``dry_run: true``, whose nine checks each record the string
  ``"would-run"``;
* 13 were ``--apply-local`` smoke tests that count rows in the LOCAL development
  database, with ``allow_empty=True`` on every check, so on the usual empty dev
  DB they assert only that a table exists. None carries a ``backup_ts``.

A drill is a restore: a real backup, restored, then queried. These tests pin
that definition, because the failure mode here is not a crash -- it is a
compliance gate that reports success for an obligation nobody performed, which
is the most expensive kind of green there is.

Stdlib only.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "verify_dr_drill_schedule.py"
_spec = importlib.util.spec_from_file_location("verify_dr_drill_schedule", SCRIPT)
mod = importlib.util.module_from_spec(_spec)
sys.modules["verify_dr_drill_schedule"] = mod
_spec.loader.exec_module(mod)


def real_drill(**overrides):
    """A minimal entry that SHOULD qualify, so each test can spoil one field."""
    entry = {
        "finished_at": "2026-08-20T02:00:00+00:00",
        "dry_run": False,
        "apply_local": False,
        "backup_ts": "2026-08-20T01:00:00+00:00",
        "checklist": [{"check": "schools_school row count >= 1", "status": "pass"}],
    }
    entry.update(overrides)
    return entry


class WhatCountsAsADrillTests(unittest.TestCase):
    def test_a_real_restore_qualifies(self):
        """Guard against a rule so strict that nothing can ever satisfy it."""
        self.assertEqual(mod._disqualifying_reason(real_drill()), "")

    def test_dry_run_does_not_count(self):
        reason = mod._disqualifying_reason(real_drill(dry_run=True))
        self.assertIn("dry-run", reason)

    def test_apply_local_smoke_test_does_not_count(self):
        """The 13 entries that made this gate green were exactly this shape."""
        reason = mod._disqualifying_reason(
            real_drill(apply_local=True, backup_ts=None)
        )
        self.assertTrue(reason, "an --apply-local smoke test counted as a DR drill")

    def test_no_backup_means_nothing_was_restored(self):
        reason = mod._disqualifying_reason(real_drill(backup_ts=None))
        self.assertIn("backup_ts", reason)

    def test_a_failing_checklist_does_not_count(self):
        """The old code never looked at status, so a failed drill counted."""
        reason = mod._disqualifying_reason(
            real_drill(checklist=[{"check": "x", "status": "fail"}])
        )
        self.assertIn("failing", reason)

    def test_an_empty_checklist_does_not_count(self):
        reason = mod._disqualifying_reason(real_drill(checklist=[]))
        self.assertIn("checklist", reason)


class LiveLogTests(unittest.TestCase):
    """The committed log, read honestly."""

    def test_rejected_entries_are_explained(self):
        """A bare 'overdue' invites moving the date; the reasons must be visible."""
        rejected = mod._rejected_summary()
        for reason, count in rejected.items():
            with self.subTest(reason=reason):
                self.assertGreater(count, 0)
                self.assertGreater(
                    len(reason.split()), 3, "reason too terse to act on"
                )

    def test_qualifying_drills_are_all_real(self):
        """Whatever qualifies must satisfy the predicate -- no back door."""
        for _when, entry in mod._qualifying_drills():
            with self.subTest(finished_at=entry.get("finished_at")):
                self.assertEqual(mod._disqualifying_reason(entry), "")


if __name__ == "__main__":
    unittest.main()
