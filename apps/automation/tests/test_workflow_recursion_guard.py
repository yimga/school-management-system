"""Tests for the workflow recursion depth-limit guard.

12-pillar audit P4 follow-up. The executor must refuse to fire a
workflow when the incoming event payload reports a nesting count
beyond ``MAX_WORKFLOW_DEPTH``. This prevents the trigger A → workflow
B → trigger A class of loop the audit named.

These are SimpleTestCase tests — the bail-out runs before any DB
fetch, so no migration / model state is needed.
"""

from __future__ import annotations

from django.test import TestCase

from apps.automation.visual_executor import MAX_WORKFLOW_DEPTH, run_workflow


class WorkflowRecursionGuardTests(TestCase):
    def test_max_workflow_depth_is_sane(self):
        # Sanity check: depth ceiling must be a small positive int so a
        # single-digit nesting is enough to catch real recursion bugs
        # without throttling legitimate sequential workflow chains.
        self.assertIsInstance(MAX_WORKFLOW_DEPTH, int)
        self.assertGreater(MAX_WORKFLOW_DEPTH, 0)
        self.assertLessEqual(MAX_WORKFLOW_DEPTH, 20)

    def test_depth_zero_does_not_bail(self):
        # depth=0 (no recursion) should fall through to the model lookup
        # and return workflow_not_found (no workflow with id 99999999),
        # NOT the recursion-limit error.
        result = run_workflow(99999999, {"_workflow_depth": 0})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "workflow_not_found")

    def test_depth_below_limit_does_not_bail(self):
        result = run_workflow(99999999, {"_workflow_depth": MAX_WORKFLOW_DEPTH})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "workflow_not_found")

    def test_depth_above_limit_refuses(self):
        result = run_workflow(
            99999999, {"_workflow_depth": MAX_WORKFLOW_DEPTH + 1}
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "workflow_recursion_limit")
        self.assertEqual(result["depth"], MAX_WORKFLOW_DEPTH + 1)
        self.assertEqual(result["workflow_id"], 99999999)

    def test_non_int_depth_treated_as_zero(self):
        # Defensive: malformed payload (string, None, dict) must not crash.
        for bad in (None, "not-an-int", {"nested": 1}, [], object()):
            result = run_workflow(99999999, {"_workflow_depth": bad})
            self.assertFalse(result["ok"])
            self.assertEqual(
                result["error"], "workflow_not_found",
                f"bad payload {bad!r} should fall through, not trip recursion guard",
            )

    def test_missing_depth_key_treated_as_zero(self):
        result = run_workflow(99999999, {})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "workflow_not_found")

    def test_non_dict_payload_does_not_crash(self):
        for bad_payload in (None, "string", 123, [1, 2, 3]):
            # Should not raise -- guards must be defensive against any
            # caller that passes a non-dict event_payload.
            result = run_workflow(99999999, bad_payload)
            self.assertFalse(result["ok"])
