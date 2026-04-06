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

    def test_phase_twelve_title_is_branding_neutral(self):
        from apps.siteconfig.management.commands.seed_cursor_twelve_phases import (
            CURSOR_PHASE_PLAN,
        )

        _, title, _ = CURSOR_PHASE_PLAN[-1]
        self.assertIn("Branding residue", title)
        self.assertNotIn("Gilead", title)

    def test_parser_accepts_branding_neutral_residue_flags(self):
        from apps.siteconfig.management.commands.seed_cursor_twelve_phases import Command

        parser = Command().create_parser("manage.py", "seed_cursor_twelve_phases")
        options = parser.parse_args(
            [
                "--strict-branding-residue-lint",
                "--skip-branding-residue-lint",
            ]
        )

        self.assertTrue(options.strict_residue_lint)
        self.assertTrue(options.skip_residue_lint)

    def test_parser_keeps_legacy_residue_aliases(self):
        from apps.siteconfig.management.commands.seed_cursor_twelve_phases import Command

        parser = Command().create_parser("manage.py", "seed_cursor_twelve_phases")
        options = parser.parse_args(
            [
                "--strict-gilead-lint",
                "--skip-gilead-lint",
            ]
        )

        self.assertTrue(options.strict_residue_lint)
        self.assertTrue(options.skip_residue_lint)
