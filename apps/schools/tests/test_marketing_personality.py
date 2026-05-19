"""Marketing page personality registry."""
from django.test import SimpleTestCase

from apps.schools.marketing_personality import (
    marketing_personality_context,
    resolve_marketing_personality,
)


class MarketingPersonalityTest(SimpleTestCase):
    def test_home_slug(self):
        p = resolve_marketing_personality("home")
        self.assertEqual(p["id"], "home")
        self.assertEqual(p["hero_tone"], "editorial-warm")

    def test_platform_admissions_slug(self):
        p = resolve_marketing_personality("platform-admissions")
        self.assertEqual(p["id"], "platform-admissions")
        self.assertEqual(p["eyebrow_motif"], "funnel")

    def test_lane_finance_short_slug(self):
        p = resolve_marketing_personality("finance")
        self.assertEqual(p["id"], "lane-finance")

    def test_solutions_persona_prefix(self):
        p = resolve_marketing_personality("solutions-for-private-schools")
        self.assertEqual(p["id"], "solutions-persona")

    def test_context_keys(self):
        ctx = marketing_personality_context("pricing")
        self.assertEqual(ctx["marketing_personality_id"], "pricing")
        self.assertIn("marketing_personality", ctx)
