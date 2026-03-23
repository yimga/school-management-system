"""
§0.2.1.6 — Super-premium phased gates: script parity + in-product proof partial on key surfaces.
"""

import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase, override_settings


ROOT = Path(__file__).resolve().parents[3]
PARTIAL = "schools/partials/wedge_super_premium_proof.html"
TEMPLATES_WITH_PROOF = [
    "schools/super_trust_center.html",
    "schools/super_geography.html",
    "schools/super_curriculum_packs.html",
    "schools/super_one_sis_any_lms.html",
    "schools/super_he_pack.html",
    "schools/super_advancement_hub.html",
    "schools/super_education_systems.html",
    "schools/super_learning_delivery_packs.html",
    "schools/super_ministry_report_stubs.html",
    "schools/super_group_campuses.html",
    "schools/super_migration_cloud.html",
]


@override_settings(ALLOWED_HOSTS=["*"])
class WedgeSuperPremiumPhasesTests(SimpleTestCase):
    def test_validate_wedge_super_premium_phases_script_passes(self):
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate_wedge_super_premium_phases.py"), "--phase", "all"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            r.returncode,
            0,
            f"validate_wedge_super_premium_phases failed:\n{r.stdout}\n{r.stderr}",
        )

    def test_proof_partial_included_on_key_wedge_templates(self):
        needle = f'include "{PARTIAL}"'
        for rel in TEMPLATES_WITH_PROOF:
            path = ROOT / "templates" / rel
            with self.subTest(template=rel):
                self.assertTrue(path.exists(), f"missing {path}")
                text = path.read_text(encoding="utf-8", errors="replace")
                self.assertIn(needle, text, f"{rel} must include {PARTIAL}")
