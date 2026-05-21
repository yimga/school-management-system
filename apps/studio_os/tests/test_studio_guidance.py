"""Studio in-context guidance catalog and template wiring."""

from django.test import SimpleTestCase

from apps.studio_os.studio_guidance import (
    LAUNCH_PANE_GUIDANCE,
    MODE_GUIDANCE,
    apply_studio_guidance_to_context,
    enrich_launch_left_rail,
    get_active_guidance,
)


class StudioGuidanceCatalogTests(SimpleTestCase):
    def test_all_modes_have_guidance(self):
        for mode_id in ("experience", "automation", "output", "launch", "control"):
            self.assertIn(mode_id, MODE_GUIDANCE)
            self.assertTrue(MODE_GUIDANCE[mode_id]["questions"])

    def test_launch_panes_have_info_copy(self):
        expected = {
            "overview",
            "onboarding",
            "plan",
            "infrastructure",
            "checklist",
        }
        self.assertTrue(expected.issubset(LAUNCH_PANE_GUIDANCE.keys()))

    def test_get_active_guidance_launch_pane(self):
        g = get_active_guidance(mode="launch", launch_pane="onboarding")
        self.assertIsNotNone(g)
        self.assertIn("pane_hint", g)
        self.assertGreaterEqual(len(g["questions"]), 2)

    def test_enrich_launch_left_rail(self):
        items = enrich_launch_left_rail(
            [{"label": "X", "url": "/u", "pane": "onboarding"}]
        )
        self.assertEqual(items[0]["info_title"], str(LAUNCH_PANE_GUIDANCE["onboarding"]["title"]))

    def test_apply_studio_guidance_to_context(self):
        ctx = {
            "studio_modes": [{"id": "launch", "label": "Launch", "description": "d"}],
            "launch_left_rail": [{"label": "L", "url": "/l", "pane": "plan"}],
            "launch_pane": "plan",
        }
        apply_studio_guidance_to_context(ctx, mode="launch")
        self.assertIn("studio_guidance", ctx)
        self.assertIn("guidance_tip", ctx["studio_modes"][0])
        self.assertIn("info_body", ctx["launch_left_rail"][0])
