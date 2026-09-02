"""Phase 1 marketing foundation regression tests."""

from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from django.test import SimpleTestCase

from apps.schools.tests.test_marketing_phase0_visual_truth import assert_no_exact_plan_pound_teasers
from apps.siteconfig.tests._template_nodes import assert_markup, assert_wires


REPO_ROOT = Path(__file__).resolve().parents[3]
LANDING = REPO_ROOT / "templates" / "schools" / "marketing_landing_v2.html"
BASE_MARKETING = REPO_ROOT / "templates" / "marketing" / "base_marketing.html"
BELL_CLOCK = REPO_ROOT / "templates" / "marketing" / "components" / "_bell_clock_sticky.html"


class MarketingPhase1AssetsTest(SimpleTestCase):
    def test_schoolhouse_and_v3_css_exist(self) -> None:
        for rel in (
            "static/marketing/css/tokens-schoolhouse.css",
            "static/marketing/css/marketing-v3-shell.css",
            "static/marketing/css/marketing-v3-narrative.css",
            "static/marketing/css/marketing-v3-dashboards.css",
        ):
            self.assertTrue((REPO_ROOT / rel).is_file(), rel)

    def test_v3_js_exists(self) -> None:
        for rel in (
            "static/marketing/js/theme-toggle.js",
            "static/marketing/js/scroll-narrative.js",
            "static/marketing/js/rotating-headline.js",
        ):
            self.assertTrue((REPO_ROOT / rel).is_file(), rel)

    def test_core_partials_exist(self) -> None:
        for rel in (
            "templates/marketing/components/_day_role_story.html",
            "templates/marketing/components/_bell_clock_sticky.html",
            "templates/marketing/components/_persona_tabs.html",
            "templates/marketing/components/_dashboard_frame.html",
            "templates/marketing/components/_rotating_headline.html",
            "templates/marketing/components/_theme_toggle.html",
            "templates/marketing/components/_product_proof_block.html",
        ):
            self.assertTrue((REPO_ROOT / rel).is_file(), rel)


class MarketingPhase1HomeWiringTest(SimpleTestCase):
    def test_home_includes_day_role_story_shell(self) -> None:
        text = LANDING.read_text(encoding="utf-8")
        # "includes" is an {% include %}: three of the four names below are
        # partials the home page must actually pull in, and a filename left in
        # a comment pulls in nothing. mkt-day-role-toggle.js is a {% static %}
        # argument and stays a read, as does the whole-text handoff to
        # assert_no_exact_plan_pound_teasers below.
        assert_wires(
            self,
            LANDING,
            "marketing/components/_day_role_story.html",
            "marketing/components/_rotating_headline.html",
            "marketing/components/_product_proof_block.html",
        )
        assert_markup(self, LANDING, "mkt-edt-voices--compact")
        assert_markup(self, BELL_CLOCK, "data-mkt-bell-clock")
        self.assertIn("_day_role_story.html", text)
        self.assertIn("mkt-day-role-toggle.js", text)
        self.assertIn("_rotating_headline.html", text)
        self.assertIn("_product_proof_block.html", text)
        self.assertIn("data-mkt-bell-clock", (REPO_ROOT / "templates/marketing/components/_bell_clock_sticky.html").read_text(encoding="utf-8"))
        self.assertIn("mkt-edt-voices--compact", text)
        assert_no_exact_plan_pound_teasers(self, text)

    def test_base_marketing_loads_v3_assets(self) -> None:
        text = BASE_MARKETING.read_text(encoding="utf-8")
        # The four asset names are {% static %} ARGUMENTS -- not emitted text,
        # and this shell does not render standalone -- so they stay reads. The
        # theme attribute is markup the shell has to put on the page for
        # theme-toggle.js to have anything to flip, so the engine answers it.
        assert_markup(self, BASE_MARKETING, 'data-theme="light"')
        self.assertIn("marketing-critical.min.css", text)
        self.assertIn("marketing-enhanced.min.css", text)
        self.assertIn("scroll-narrative.js", text)
        self.assertIn("theme-toggle.js", text)
        self.assertIn('data-theme="light"', text)

    def test_marketing_css_bundles_exist(self) -> None:
        for rel in (
            "static/marketing/css/marketing-critical.min.css",
            "static/marketing/css/marketing-enhanced.min.css",
            "static/marketing/fonts/source-serif-4/source-serif-4-latin-400-normal.woff2",
        ):
            self.assertTrue((REPO_ROOT / rel).is_file(), rel)

    def test_marketing_public_shell_gate_passes(self) -> None:
        import subprocess
        import sys

        proc = subprocess.run(
            [sys.executable, "scripts/verify_marketing_public_shell.py"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)

    @unittest.skipUnless(
        shutil.which("ffmpeg"),
        "ffmpeg required: verify_marketing_frontend_completion runs "
        "verify_marketing_site_seeded, which fails on the 275B placeholder marketing "
        "loop mp4s that only ffmpeg can regenerate from the hero — an environment/asset "
        "dependency, not a bug.",
    )
    def test_marketing_frontend_completion_gate_passes(self) -> None:
        import subprocess
        import sys

        proc = subprocess.run(
            [sys.executable, "scripts/verify_marketing_frontend_completion.py"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
