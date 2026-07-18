from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = ROOT / "templates" / "platform_runtime"


class GovernedInstallationUXFlowTests(SimpleTestCase):
    def test_platform_install_surfaces_show_stepper_risk_approval_health_and_rollback(self):
        stepper = (ROOT / "templates" / "components" / "world_class_guided_stepper.html").read_text(encoding="utf-8")
        strip = (ROOT / "templates" / "components" / "tenant_option_a_strip.html").read_text(encoding="utf-8")
        for name in ("blueprint_marketplace.html", "pack_marketplace.html", "change_requests.html"):
            with self.subTest(name=name):
                text = (TEMPLATES / name).read_text(encoding="utf-8")
                self.assertIn("tenant_option_a_strip.html", text)
                self.assertIn("hide_nav_detail", text)
                self.assertIn("option_a_show_stepper", text)
                self.assertIn("world_class_guided_stepper.html", strip)
                self.assertIn("Preview", stepper)
                self.assertIn("Simulate", stepper)
                self.assertIn("Impact", stepper)
                self.assertIn("Request approval", stepper)
                self.assertIn("Rollback", stepper)
                self.assertRegex(text, "approval|Approval")
                self.assertRegex(text, "rollback|Rollback")

    def test_tenant_install_surfaces_do_not_expose_platform_only_route(self):
        for name in ("tenant_blueprint_setup.html", "tenant_pack_setup.html"):
            with self.subTest(name=name):
                text = (TEMPLATES / name).read_text(encoding="utf-8")
                has_option_a = (
                    "tenant_option_a_strip.html" in text
                    or "tenant_blueprint_option_a_strip.html" in text
                )
                has_stepper = "world_class_guided_stepper.html" in text or has_option_a
                self.assertTrue(has_stepper, msg=f"{name} missing guided stepper / Option A strip")
                if "tenant_blueprint_option_a_strip.html" in text:
                    strip = (ROOT / "templates" / "components" / "tenant_blueprint_option_a_strip.html").read_text(
                        encoding="utf-8"
                    )
                    self.assertIn("tenant_option_a_strip.html", strip)
                if "tenant_option_a_strip.html" in text and "option_a_show_stepper" in text:
                    shared = (ROOT / "templates" / "components" / "tenant_option_a_strip.html").read_text(
                        encoding="utf-8"
                    )
                    self.assertIn("world_class_guided_stepper.html", shared)
                self.assertIn("tenant", text.lower())
                self.assertIn("rollback", text.lower())
                self.assertNotIn("/configuration/blueprints/", text)
                self.assertNotIn("/configuration/workflow-packs/", text)
