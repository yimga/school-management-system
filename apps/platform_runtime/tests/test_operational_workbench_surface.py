from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class OperationalWorkbenchSurfaceTests(SimpleTestCase):
    def test_workbench_templates_use_operational_frame_not_hero(self):
        import subprocess
        import sys

        script = ROOT / "scripts" / "verify_operational_workbench_surface.py"
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            proc.returncode,
            0,
            msg=proc.stdout + proc.stderr,
        )

    def test_last_sweep_templates_include_operational_frame(self):
        for rel in (
            "templates/marketplace/blueprint_marketplace.html",
            "templates/marketplace/installation_health.html",
            "templates/marketplace/tenant_app_catalog.html",
            "templates/platform_runtime/tenant_import_setup.html",
            "templates/platform_runtime/tenant_blueprint_setup.html",
            "templates/platform_runtime/tenant_pack_setup.html",
            "templates/finance/dashboard.html",
            "templates/marketing/pricing_packages.html",
        ):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("rmc_operational_center_frame.html", text, rel)
            self.assertNotIn("world_class_page_hero.html", text, rel)
