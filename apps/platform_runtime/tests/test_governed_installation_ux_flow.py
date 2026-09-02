from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_wires


ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = ROOT / "templates" / "platform_runtime"


class GovernedInstallationUXFlowTests(SimpleTestCase):
    def test_platform_install_surfaces_use_masthead_not_option_a_wall(self):
        """MAX Wave 5: Option-A meta strips purged; masthead + work-root own chrome."""
        for name in ("blueprint_marketplace.html", "pack_marketplace.html", "change_requests.html"):
            with self.subTest(name=name):
                text = (TEMPLATES / name).read_text(encoding="utf-8")
                self.assertNotIn("tenant_option_a_strip.html", text)
                self.assertIn("rmc_operational_center_frame.html", text)
                self.assertIn("hide_nav_detail", text)
                self.assertRegex(text, "approval|Approval")
                self.assertRegex(text, "rollback|Rollback")

    def test_tenant_install_surfaces_do_not_expose_platform_only_route(self):
        for name in ("tenant_blueprint_setup.html", "tenant_pack_setup.html"):
            with self.subTest(name=name):
                text = (TEMPLATES / name).read_text(encoding="utf-8")
                self.assertNotIn("tenant_option_a_strip.html", text)
                # Four of this test's five checks are ABSENCES, which are byte
                # questions and stay reads. The one positive is an {% include %}:
                # a commented-out frame leaves the filename in the bytes and the
                # tenant install page with no operational-center chrome at all.
                assert_wires(
                    self, TEMPLATES / name, "components/rmc_operational_center_frame.html"
                )
                self.assertNotIn("tenant_blueprint_option_a_strip.html", text)
                self.assertIn("rmc_operational_center_frame.html", text)
                self.assertIn("tenant", text.lower())
                self.assertIn("rollback", text.lower())
                self.assertNotIn("/configuration/blueprints/", text)
                self.assertNotIn("/configuration/workflow-packs/", text)
