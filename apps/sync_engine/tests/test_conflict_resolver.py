"""Tests for the offline-sync conflict resolver."""

from __future__ import annotations

import unittest

from apps.sync_engine.conflict_resolver import (
    DEFAULT_STRATEGY_PER_ENTITY,
    ResolutionStrategy,
    resolve_conflicts,
    resolve_one,
)


class ResolveOneTests(unittest.TestCase):
    def test_attendance_default_is_lww(self):
        self.assertEqual(
            DEFAULT_STRATEGY_PER_ENTITY["attendance_record"],
            ResolutionStrategy.LAST_WRITE_WINS,
        )

    def test_grade_entry_defaults_to_manual(self):
        self.assertEqual(
            DEFAULT_STRATEGY_PER_ENTITY["grade_entry"],
            ResolutionStrategy.MANUAL_REVIEW,
        )

    def test_unknown_entity_defaults_to_manual(self):
        decision = resolve_one({"entity": "exotic_thing"})
        self.assertEqual(decision["action"], "manual_review")

    def test_lww_picks_newer_remote(self):
        c = {
            "entity": "attendance_record",
            "remote_timestamp": "2026-05-08T12:00:00Z",
            "server_timestamp": "2026-05-08T11:00:00Z",
        }
        decision = resolve_one(c)
        self.assertEqual(decision["action"], "keep_remote")

    def test_lww_picks_newer_server(self):
        c = {
            "entity": "attendance_record",
            "remote_timestamp": "2026-05-08T11:00:00Z",
            "server_timestamp": "2026-05-08T12:00:00Z",
        }
        decision = resolve_one(c)
        self.assertEqual(decision["action"], "keep_server")

    def test_lww_tie_prefers_server(self):
        ts = "2026-05-08T12:00:00Z"
        c = {
            "entity": "attendance_record",
            "remote_timestamp": ts,
            "server_timestamp": ts,
        }
        decision = resolve_one(c)
        self.assertEqual(decision["action"], "keep_server")

    def test_lww_without_timestamps_falls_back_to_manual(self):
        decision = resolve_one({"entity": "attendance_record"})
        self.assertEqual(decision["action"], "manual_review")

    def test_server_authoritative_keeps_server(self):
        decision = resolve_one(
            {"entity": "user_profile"}, strategy=ResolutionStrategy.SERVER_AUTHORITATIVE
        )
        self.assertEqual(decision["action"], "keep_server")

    def test_grade_entry_never_auto_resolves_even_with_strategy_passed(self):
        # Caller can override per-entity by passing strategy explicitly.
        decision = resolve_one(
            {"entity": "grade_entry"},
            strategy=ResolutionStrategy.SERVER_AUTHORITATIVE,
        )
        self.assertEqual(decision["action"], "keep_server")
        # But the default for grade_entry remains manual_review.
        decision_default = resolve_one({"entity": "grade_entry"})
        self.assertEqual(decision_default["action"], "manual_review")


class ResolveConflictsBatchTests(unittest.TestCase):
    def test_batch_returns_one_decision_per_conflict(self):
        conflicts = [
            {"entity": "attendance_record", "remote_timestamp": "2026-05-08T12:00:00Z",
             "server_timestamp": "2026-05-08T10:00:00Z"},
            {"entity": "grade_entry"},
            {"entity": "user_profile"},
        ]
        decisions = resolve_conflicts(conflicts)
        self.assertEqual(len(decisions), 3)
        self.assertEqual(decisions[0]["decision"]["action"], "keep_remote")
        self.assertEqual(decisions[1]["decision"]["action"], "manual_review")
        self.assertEqual(decisions[2]["decision"]["action"], "keep_server")

    def test_per_entity_override_wins(self):
        c = {"entity": "attendance_record"}
        decisions = resolve_conflicts(
            [c],
            per_entity_override={"attendance_record": ResolutionStrategy.SERVER_AUTHORITATIVE},
        )
        self.assertEqual(decisions[0]["decision"]["action"], "keep_server")

    def test_strategy_kwarg_used_when_no_override(self):
        c = {"entity": "exotic_thing"}
        decisions = resolve_conflicts(
            [c],
            strategy=ResolutionStrategy.SERVER_AUTHORITATIVE,
        )
        self.assertEqual(decisions[0]["decision"]["action"], "keep_server")


if __name__ == "__main__":
    unittest.main()
