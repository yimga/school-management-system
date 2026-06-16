"""Zero-data admin dashboard: priority queue nudges setup instead of "all clear".

`_build_priority_queue` is a pure function (no DB), so these run as SimpleTestCase.
Backlog P1 #7: a brand-new school's dashboard read "queues are clear / system stable"
(i.e. "all good") when nothing was set up yet.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.dashboard.context import _build_priority_queue


class PriorityQueueSetupNudgeTests(SimpleTestCase):
    def test_zero_data_shows_setup_nudge(self):
        result = _build_priority_queue([], setup_incomplete=True)
        self.assertEqual(result[0]["label"], "Finish setting up your school")
        self.assertIn("guided-onboarding", result[0]["url"])
        self.assertEqual(result[0]["status"], "warn")

    def test_default_is_backward_compatible(self):
        # Existing callers (no setup_incomplete) keep the prior empty state.
        result = _build_priority_queue([])
        self.assertEqual(result[0]["label"], "No urgent blockers")

    def test_real_work_outranks_setup_nudge(self):
        result = _build_priority_queue(
            [{"value": 3, "status": "danger", "label": "Overdue invoices"}],
            setup_incomplete=True,
        )
        self.assertEqual(result[0]["label"], "Overdue invoices")
