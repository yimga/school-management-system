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

    def test_tenant_finance_surfaces_use_single_command_frame(self):
        dashboard = (ROOT / "templates" / "finance" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("rmc_operational_center_frame.html", dashboard)
        self.assertIn("rmc-world-class-experience.css", dashboard)
        self.assertIn('id="money-actions"', dashboard)
        self.assertIn('data-rmc-bounded-work-zone="finance-money-center"', dashboard)
        self.assertNotIn("components/rmc_os_page_header.html", dashboard)
        self.assertNotIn("components/rmc_os_action_bar.html", dashboard)

        readiness = (ROOT / "templates" / "finance" / "payment_readiness_dashboard.html").read_text(encoding="utf-8")
        self.assertIn("rmc_operational_center_frame.html", readiness)
        self.assertIn("world_class_summary_strip.html", readiness)
        self.assertIn("secondary_url=payment_money_url", readiness)
        self.assertNotIn('secondary_url="/finance/"', readiness)

    def test_bounded_work_zone_contract_is_shared(self):
        text = (ROOT / "static" / "css" / "rmc-tenant-surface-scroll-contract.css").read_text(encoding="utf-8")
        self.assertIn("[data-rmc-bounded-work-zone]", text)
        self.assertIn(".dashboard-card-scroll", text)
