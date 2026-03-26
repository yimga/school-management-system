"""Contract: twelve-phase seed plan stays aligned with SOT phase index (1-12)."""

from django.test import SimpleTestCase


class SeedCursorTwelvePhasesPlanTests(SimpleTestCase):
    def test_plan_has_twelve_phases_in_order(self):
        from apps.siteconfig.management.commands.seed_cursor_twelve_phases import (
            CURSOR_PHASE_PLAN,
        )

        self.assertEqual(len(CURSOR_PHASE_PLAN), 12)
        for i, (num, title, steps) in enumerate(CURSOR_PHASE_PLAN, start=1):
            self.assertEqual(num, i, msg=f"Phase slot {i}: expected number {i}, got {num}")
            self.assertTrue(title.strip(), msg=f"Phase {i} needs a non-empty title")
            self.assertTrue(steps, msg=f"Phase {i} must list at least one seed command")
