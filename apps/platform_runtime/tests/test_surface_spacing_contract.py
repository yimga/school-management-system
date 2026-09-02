from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_markup


ROOT = Path(__file__).resolve().parents[3]
_ADMIN_BASE_SITE = ROOT / "templates" / "admin" / "base_site.html"


class SurfaceSpacingContractTests(SimpleTestCase):
    def test_spacing_contract_css_loaded_on_shells(self):
        portal = (ROOT / "templates" / "partials" / "rmc_platform_chrome_styles.html").read_text(
            encoding="utf-8"
        )
        cp = (ROOT / "templates" / "control_plane_base.html").read_text(encoding="utf-8")
        admin = _ADMIN_BASE_SITE.read_text(encoding="utf-8")
        # On all three shells the sheet is a {% static %} argument, so it is never
        # emitted text and the source read is the only thing that can see it.
        for text, label in ((portal, "portal"), (cp, "cp"), (admin, "admin")):
            self.assertIn("rmc-surface-spacing-contract.css", text, label)
        # A shell that renders nothing loads no spacing contract either, and the
        # reads above cannot tell that apart. base_site.html is the template this
        # case is bound to, so assert its own layout-owner marker is EMITTED.
        assert_markup(
            self, _ADMIN_BASE_SITE, 'data-rmc-admin-layout-owner="emergency-v17"'
        )

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
