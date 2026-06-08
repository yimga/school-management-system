"""Tests for offline event envelope (batch 1532)."""

from django.test import SimpleTestCase

from apps.sync_engine.event_envelope import (
    OfflineEnvelopeError,
    build_envelope,
    validate_envelope_dict,
)


class OfflineEventEnvelopeTests(SimpleTestCase):
    def test_build_envelope_ok(self):
        payload = build_envelope(
            entity="attendance_record",
            entity_id="1",
            attribute_key="status",
            attribute_value="present",
            client_id="c1",
        )
        self.assertEqual(payload["entity"], "attendance_record")
        self.assertEqual(payload["merge_strategy"], "causal_lww")
        self.assertGreaterEqual(payload["policy_version"], 1)
        self.assertLessEqual(payload["bytes_estimate"], 1024)

    def test_grade_alias_is_stamped_manual_review(self):
        env = validate_envelope_dict(
            {
                "entity": "grade",
                "entity_id": "1",
                "attribute_key": "exam_score",
                "attribute_value": 18,
                "client_id": "device-a",
            }
        )
        self.assertEqual(env.entity, "grade_entry")
        self.assertEqual(env.merge_strategy, "manual_review")

    def test_rejects_oversize_without_allow(self):
        huge = "x" * 2000
        with self.assertRaises(OfflineEnvelopeError):
            validate_envelope_dict(
                {
                    "entity": "note",
                    "entity_id": "1",
                    "attribute_key": "body",
                    "attribute_value": huge,
                    "deterministic_timestamp": "2026-05-28T00:00:00+00:00",
                    "client_id": "c",
                }
            )
