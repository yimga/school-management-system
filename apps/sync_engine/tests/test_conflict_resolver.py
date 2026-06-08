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

    def test_lww_picks_newer_remote_causal_rank(self):
        c = {
            "entity": "attendance_record",
            "remote_clock": {"lamport": 12, "replica_id": "device-a"},
            "server_clock": {"lamport": 11, "replica_id": "server"},
        }
        decision = resolve_one(c)
        self.assertEqual(decision["action"], "keep_remote")

    def test_lww_picks_newer_server_causal_rank(self):
        c = {
            "entity": "attendance_record",
            "remote_clock": "100:1:device-a",
            "server_clock": "100:2:server",
        }
        decision = resolve_one(c)
        self.assertEqual(decision["action"], "keep_server")

    def test_lww_tie_prefers_server(self):
        clock = "100:1:device-a"
        c = {
            "entity": "attendance_record",
            "remote_clock": clock,
            "server_clock": clock,
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

    def test_grade_entry_rejects_weaker_override(self):
        decision = resolve_one(
            {"entity": "grade_entry"},
            strategy=ResolutionStrategy.SERVER_AUTHORITATIVE,
        )
        self.assertEqual(decision["action"], "manual_review")
        self.assertTrue(decision["override_blocked"])
        self.assertTrue(decision["protected_policy"])


class ResolveConflictsBatchTests(unittest.TestCase):
    def test_batch_returns_one_decision_per_conflict(self):
        conflicts = [
            {"entity": "attendance_record",
             "remote_clock": {"lamport": 2, "replica_id": "device"},
             "server_clock": {"lamport": 1, "replica_id": "server"}},
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

    def test_per_entity_override_cannot_weaken_protected_policy(self):
        decisions = resolve_conflicts(
            [{"entity": "grade"}],
            per_entity_override={
                "grade_entry": ResolutionStrategy.SERVER_AUTHORITATIVE
            },
        )
        self.assertEqual(decisions[0]["decision"]["action"], "manual_review")
        self.assertTrue(decisions[0]["decision"]["override_blocked"])

    def test_unknown_entity_blocks_global_override(self):
        c = {"entity": "exotic_thing"}
        decisions = resolve_conflicts(
            [c],
            strategy=ResolutionStrategy.SERVER_AUTHORITATIVE,
        )
        self.assertEqual(decisions[0]["decision"]["action"], "manual_review")
        self.assertTrue(decisions[0]["decision"]["override_blocked"])


if __name__ == "__main__":
    unittest.main()
