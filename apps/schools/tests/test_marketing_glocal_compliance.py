"""GLOCAL + VISUAL-ENGINE compliance (manifest, sections, no iframes)."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_wires

REPO = Path(__file__).resolve().parents[3]


class MarketingGlocalComplianceTests(SimpleTestCase):
    def test_homepage_includes_four_personality_sections(self):
        landing = REPO / "templates" / "schools" / "marketing_landing_v2.html"
        # "Includes four personality sections" is four {% include %}s, and a
        # filename left behind in a comment includes nothing. Ask the parser.
        assert_wires(
            self,
            landing,
            "marketing/partials/sections/_sovereign_kernel.html",
            "marketing/partials/sections/_clinical_ledger.html",
            "marketing/partials/sections/_rugged_engine.html",
            "marketing/partials/sections/_fluid_classroom.html",
        )

    def test_manifest_homepage_sections(self):
        manifest = json.loads(
            (REPO / "docs" / "generated" / "marketing_media_manifest.json").read_text(encoding="utf-8")
        )
        sections = set(manifest.get("homepage_sections") or [])
        self.assertTrue(
            {"sovereign_kernel", "clinical_ledger", "rugged_engine", "fluid_classroom"}.issubset(sections)
        )

    @unittest.skipUnless(
        shutil.which("ffmpeg"),
        "ffmpeg required: the gate derives real, regionally-distinct marketing loop "
        "videos from the hero via compress_marketing_loops_from_hero; without ffmpeg "
        "only 275B placeholders exist (identical per region), so this build/asset "
        "pipeline check cannot pass in an ffmpeg-less environment.",
    )
    def test_glocal_visual_engine_gate(self):
        proc = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "verify_marketing_glocal_visual_engine.py")],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
