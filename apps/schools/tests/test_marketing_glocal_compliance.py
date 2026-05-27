"""GLOCAL + VISUAL-ENGINE compliance (manifest, sections, no iframes)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

REPO = Path(__file__).resolve().parents[3]


class MarketingGlocalComplianceTests(SimpleTestCase):
    def test_homepage_includes_four_personality_sections(self):
        landing = REPO / "templates" / "schools" / "marketing_landing_v2.html"
        text = landing.read_text(encoding="utf-8")
        for partial in (
            "_sovereign_kernel.html",
            "_clinical_ledger.html",
            "_rugged_engine.html",
            "_fluid_classroom.html",
        ):
            self.assertIn(partial, text)

    def test_manifest_homepage_sections(self):
        manifest = json.loads(
            (REPO / "docs" / "generated" / "marketing_media_manifest.json").read_text(encoding="utf-8")
        )
        sections = set(manifest.get("homepage_sections") or [])
        self.assertTrue(
            {"sovereign_kernel", "clinical_ledger", "rugged_engine", "fluid_classroom"}.issubset(sections)
        )

    def test_glocal_visual_engine_gate(self):
        proc = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "verify_marketing_glocal_visual_engine.py")],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
