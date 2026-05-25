from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class SurfaceSpacingContractTests(SimpleTestCase):
    def test_spacing_contract_css_loaded_on_shells(self):
        portal = (ROOT / "templates" / "partials" / "rmc_platform_chrome_styles.html").read_text(
            encoding="utf-8"
        )
        cp = (ROOT / "templates" / "control_plane_base.html").read_text(encoding="utf-8")
        admin = (ROOT / "templates" / "admin" / "base_site.html").read_text(encoding="utf-8")
        for text, label in ((portal, "portal"), (cp, "cp"), (admin, "admin")):
            self.assertIn("rmc-surface-spacing-contract.css", text, label)

    def test_no_double_quote_workbench_typo_in_templates(self):
        hits = []
        for path in (ROOT / "templates").rglob("*.html"):
            if 'operational-workbench""' in path.read_text(encoding="utf-8", errors="replace"):
                hits.append(str(path.relative_to(ROOT)))
        self.assertEqual(hits, [])

    def test_spacing_audit_script_passes_medium(self):
        import subprocess
        import sys

        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "audit_surface_spacing_contract.py"), "--strict"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
