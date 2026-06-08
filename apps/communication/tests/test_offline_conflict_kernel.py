"""Wave S-E (v3.96.1 — 2026-05-26) — Offline conflict resolution tests."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.communication.offline_conflict_kernel import (
    LATER_WINS,
    LOCAL_WINS,
    MANUAL_REVIEW,
    SyncRecord,
    get_default_strategy,
    resolve_batch,
    resolve_conflict,
)


def _local(rec_type, key, payload, ts):
    return SyncRecord(
        record_type=rec_type, record_key=key, payload=payload,
        timestamp_iso=ts, source="local",
    )


def _remote(rec_type, key, payload, ts):
    return SyncRecord(
        record_type=rec_type, record_key=key, payload=payload,
        timestamp_iso=ts, source="remote",
    )


class DefaultPolicyTests(SimpleTestCase):

    def test_attendance_default_later_wins(self):
        self.assertEqual(get_default_strategy("attendance"), LATER_WINS)

    def test_grade_default_manual_review(self):
        self.assertEqual(get_default_strategy("grade"), MANUAL_REVIEW)

    def test_profile_default_is_server_authoritative(self):
        self.assertEqual(get_default_strategy("profile"), "REMOTE_WINS")

    def test_unknown_type_defaults_to_manual(self):
        self.assertEqual(get_default_strategy("invented"), MANUAL_REVIEW)


class LaterWinsTests(SimpleTestCase):

    def test_local_newer_wins(self):
        l = _local("attendance", "s1:2026-05-26", {"status": "present"},
                   "2026-05-26T10:00:00+00:00")
        r = _remote("attendance", "s1:2026-05-26", {"status": "absent"},
                    "2026-05-26T09:00:00+00:00")
        out = resolve_conflict(local=l, remote=r)
        self.assertEqual(out.winner_source, "local")
        self.assertEqual(out.winner_payload["status"], "present")

    def test_remote_newer_wins(self):
        l = _local("attendance", "s1:2026-05-26", {"status": "present"},
                   "2026-05-26T08:00:00+00:00")
        r = _remote("attendance", "s1:2026-05-26", {"status": "late"},
                    "2026-05-26T09:30:00+00:00")
        out = resolve_conflict(local=l, remote=r)
        self.assertEqual(out.winner_source, "remote")
        self.assertEqual(out.winner_payload["status"], "late")

    def test_tied_timestamps_forces_manual_review(self):
        l = _local("attendance", "s1:2026-05-26", {"status": "present"},
                   "2026-05-26T10:00:00+00:00")
        r = _remote("attendance", "s1:2026-05-26", {"status": "absent"},
                    "2026-05-26T10:00:00+00:00")
        out = resolve_conflict(local=l, remote=r)
        self.assertTrue(out.manual_review_required)
        self.assertEqual(out.notes, "tied_timestamps")


class RemoteWinsTests(SimpleTestCase):

    def test_submission_uses_remote(self):
        l = _local("homework_submission", "hw1:s1",
                   {"text": "draft"}, "2026-05-26T10:00:00+00:00")
        r = _remote("homework_submission", "hw1:s1",
                    {"text": "final"}, "2026-05-26T09:00:00+00:00")
        out = resolve_conflict(local=l, remote=r)
        self.assertEqual(out.winner_source, "remote")
        # Even though local has later timestamp, REMOTE_WINS by policy.
        self.assertEqual(out.winner_payload["text"], "final")


class ExplicitMergeFieldsTests(SimpleTestCase):

    def test_non_conflicting_fields_merged(self):
        l = _local(
            "contact_preferences", "u1",
            {"email": "old@x.com", "phone": "+1-555-1234"},
            "2026-05-26T10:00:00+00:00",
        )
        r = _remote(
            "contact_preferences", "u1",
            {"email": "old@x.com", "address": "123 Main"},
            "2026-05-26T09:00:00+00:00",
        )
        out = resolve_conflict(local=l, remote=r)
        # phone (local only) + address (remote only) + email (same) all merge.
        self.assertFalse(out.manual_review_required)
        self.assertEqual(out.winner_payload["email"], "old@x.com")
        self.assertEqual(out.winner_payload["phone"], "+1-555-1234")
        self.assertEqual(out.winner_payload["address"], "123 Main")

    def test_conflicting_fields_flagged(self):
        l = _local(
            "contact_preferences", "u1",
            {"email": "local@x.com"},
            "2026-05-26T10:00:00+00:00",
        )
        r = _remote(
            "contact_preferences", "u1",
            {"email": "remote@x.com"},
            "2026-05-26T09:00:00+00:00",
        )
        out = resolve_conflict(local=l, remote=r)
        self.assertTrue(out.manual_review_required)
        self.assertIn("conflicting_fields:email", out.notes)
        # Default conflicting value = remote.
        self.assertEqual(out.winner_payload["email"], "remote@x.com")


class ManualReviewTests(SimpleTestCase):

    def test_grade_always_manual(self):
        l = _local("grade", "as1:s1",
                   {"score": 85}, "2026-05-26T10:00:00+00:00")
        r = _remote("grade", "as1:s1",
                    {"score": 90}, "2026-05-26T09:00:00+00:00")
        out = resolve_conflict(local=l, remote=r)
        self.assertTrue(out.manual_review_required)


class StrategyOverrideTests(SimpleTestCase):

    def test_override_grade_to_local_wins_is_blocked(self):
        l = _local("grade", "as1:s1",
                   {"score": 85}, "2026-05-26T10:00:00+00:00")
        r = _remote("grade", "as1:s1",
                    {"score": 90}, "2026-05-26T09:00:00+00:00")
        out = resolve_conflict(local=l, remote=r, strategy=LOCAL_WINS)
        self.assertTrue(out.manual_review_required)
        self.assertEqual(out.notes, "manual_review_required_by_policy")

    def test_unknown_strategy_rejected(self):
        l = _local("attendance", "s1:2026-05-26", {"status": "present"},
                   "2026-05-26T10:00:00+00:00")
        r = _remote("attendance", "s1:2026-05-26", {"status": "absent"},
                    "2026-05-26T09:00:00+00:00")
        with self.assertRaises(ValueError):
            resolve_conflict(local=l, remote=r, strategy="GIBBERISH")


class IdenticalPayloadTests(SimpleTestCase):

    def test_no_diff_short_circuits(self):
        l = _local("attendance", "s1:2026-05-26", {"status": "present"},
                   "2026-05-26T10:00:00+00:00")
        r = _remote("attendance", "s1:2026-05-26", {"status": "present"},
                    "2026-05-26T10:00:00+00:00")
        out = resolve_conflict(local=l, remote=r)
        self.assertEqual(out.notes, "no_diff")
        self.assertFalse(out.manual_review_required)


class MismatchedRecordsTests(SimpleTestCase):

    def test_type_mismatch_raises(self):
        l = _local("attendance", "k", {}, "2026-05-26T10:00:00+00:00")
        r = _remote("grade", "k", {}, "2026-05-26T10:00:00+00:00")
        with self.assertRaises(ValueError):
            resolve_conflict(local=l, remote=r)

    def test_key_mismatch_raises(self):
        l = _local("attendance", "k1", {}, "2026-05-26T10:00:00+00:00")
        r = _remote("attendance", "k2", {}, "2026-05-26T10:00:00+00:00")
        with self.assertRaises(ValueError):
            resolve_conflict(local=l, remote=r)


class ResolveBatchTests(SimpleTestCase):

    def test_mixed_batch_tally(self):
        pairs = [
            # auto-resolved: attendance later wins
            (
                _local("attendance", "s1:2026-05-26", {"status": "present"},
                       "2026-05-26T10:00:00+00:00"),
                _remote("attendance", "s1:2026-05-26", {"status": "absent"},
                        "2026-05-26T09:00:00+00:00"),
            ),
            # manual review: grade
            (
                _local("grade", "as1:s1", {"score": 85},
                       "2026-05-26T10:00:00+00:00"),
                _remote("grade", "as1:s1", {"score": 90},
                        "2026-05-26T09:00:00+00:00"),
            ),
            # identical: no-op
            (
                _local("attendance", "s2:2026-05-26", {"status": "present"},
                       "2026-05-26T10:00:00+00:00"),
                _remote("attendance", "s2:2026-05-26", {"status": "present"},
                        "2026-05-26T10:00:00+00:00"),
            ),
        ]
        report = resolve_batch(pairs=pairs)
        self.assertEqual(report.auto_resolved, 1)
        self.assertEqual(report.manual_review, 1)
        self.assertEqual(report.no_op_identical, 1)
