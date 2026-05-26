"""Wave P-B (v3.95.1 — 2026-05-26) — Agentic AI runner bridge tests."""

from __future__ import annotations

from django.test import SimpleTestCase

from services.ai_agentic import ActionContext, ProposedAction
from services.ai_agentic_runners import (
    get_runner_for,
    list_bridged_actions,
    run_draft_parent_announcement,
    run_summarize_attendance_report,
    run_summarize_outstanding_fees,
)


def _ctx():
    return ActionContext(
        tenant_id="t1", user_id="u1", user_roles=("TEACHER",),
    )


class RegistryTests(SimpleTestCase):

    def test_list_bridged_actions(self):
        actions = list_bridged_actions()
        self.assertIn("summarize_attendance_report", actions)
        self.assertIn("summarize_outstanding_fees", actions)
        self.assertIn("draft_parent_announcement", actions)

    def test_get_runner_for_known_action(self):
        self.assertIsNotNone(get_runner_for("summarize_attendance_report"))

    def test_get_runner_for_unknown_returns_none(self):
        # Mutating actions are intentionally not auto-bridged.
        self.assertIsNone(get_runner_for("send_parent_message"))
        self.assertIsNone(get_runner_for("apply_fee_waiver"))
        self.assertIsNone(get_runner_for("purge_student_record"))
        self.assertIsNone(get_runner_for("nonexistent"))


class AttendanceRunnerTests(SimpleTestCase):

    def test_missing_class_id_returns_friendly_summary(self):
        result = run_summarize_attendance_report(
            ProposedAction(action="summarize_attendance_report", params={}),
            _ctx(),
        )
        self.assertIn("class_id", result["summary"])
        # Metrics dict is empty when no class_id was provided.
        self.assertEqual(result["metrics"], {})

    def test_with_class_id_handles_missing_model_gracefully(self):
        # The runner imports AttendanceRecord lazily; absent or empty data
        # should not raise.
        result = run_summarize_attendance_report(
            ProposedAction(action="summarize_attendance_report",
                            params={"class_id": "5A"}),
            _ctx(),
        )
        self.assertIn("metrics", result)
        # Either "No attendance recorded" or an actual summary; either way,
        # no exception.
        self.assertIn("summary", result)


class FeesRunnerTests(SimpleTestCase):

    def test_no_class_id_returns_platform_wide_summary(self):
        result = run_summarize_outstanding_fees(
            ProposedAction(action="summarize_outstanding_fees", params={}),
            _ctx(),
        )
        self.assertIn("totals", result)
        self.assertIn("summary", result)

    def test_with_class_id_runs_without_error(self):
        result = run_summarize_outstanding_fees(
            ProposedAction(action="summarize_outstanding_fees",
                            params={"class_id": "5A"}),
            _ctx(),
        )
        self.assertIn("totals", result)


class AnnouncementRunnerTests(SimpleTestCase):

    def test_default_audience(self):
        result = run_draft_parent_announcement(
            ProposedAction(action="draft_parent_announcement", params={}),
            _ctx(),
        )
        self.assertIn("Dear parents", result["draft"])
        self.assertEqual(result["audience"], "all_parents")
        self.assertEqual(result["locale"], "en")
        self.assertGreater(result["estimated_read_seconds"], 0)

    def test_audience_label_mapping(self):
        result = run_draft_parent_announcement(
            ProposedAction(action="draft_parent_announcement",
                            params={"audience": "year_12_parents",
                                    "topic": "exam dates",
                                    "locale": "fr"}),
            _ctx(),
        )
        self.assertIn("Year 12", result["draft"])
        self.assertIn("exam dates", result["draft"])
        self.assertEqual(result["locale"], "fr")

    def test_unknown_audience_falls_back_to_default(self):
        result = run_draft_parent_announcement(
            ProposedAction(action="draft_parent_announcement",
                            params={"audience": "moon_colony"}),
            _ctx(),
        )
        self.assertIn("Dear parents", result["draft"])
