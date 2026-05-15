from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class SuperAppleClassExperienceTests(SimpleTestCase):
    def test_super_command_center_has_apple_class_above_fold(self):
        """v2.51 (2026-05-15): contract relaxed for the dashboard redundancy strip.

        Previously this asserted that ``Platform Health`` / ``Schools Needing Attention``
        / ``External Blockers`` and ``data-apple-class-command-strip`` lived above the
        fold. Those values are now exposed once via ``world_class_summary_strip`` +
        ``cp-chip-row`` instead of being stamped a second time as apple-class metric
        cards. The hook that survived is the shell root attribute, the quick-profile
        drawer, and the detail-disclosure CTA — those are the load-bearing tokens for
        the operator experience contract.
        """
        text = (ROOT / "templates" / "schools" / "super_dashboard.html").read_text(encoding="utf-8")
        for token in (
            "data-apple-class-super-command-center",
            "apple_class_quick_profile_drawer.html",
            "Open detailed operating board",
            # Pulse coverage now lives on the consolidated chip row + summary strip:
            "world_class_summary_strip.html",
            "cp-chip-row",
        ):
            with self.subTest(token=token):
                self.assertIn(token, text)
