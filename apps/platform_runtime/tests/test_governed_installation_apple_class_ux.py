from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class GovernedInstallationAppleClassTests(SimpleTestCase):
    def test_governed_surfaces_show_visual_flow_and_dependencies(self):
        paths = [
            ROOT / "templates" / "platform_runtime" / "change_requests.html",
            ROOT / "templates" / "platform_runtime" / "blueprint_marketplace.html",
            ROOT / "templates" / "platform_runtime" / "pack_marketplace.html",
        ]
        strip = (ROOT / "templates" / "components" / "tenant_option_a_strip.html").read_text(encoding="utf-8")
        nav = (ROOT / "apps" / "platform_runtime" / "operational_center_nav.py").read_text(encoding="utf-8")
        for path in paths:
            text = f"{path.read_text(encoding='utf-8')}\n{nav}\n{strip}"
            with self.subTest(path=path.name):
                self.assertIn("data-apple-class-governed-installation", text)
                # Option A nests the guided stepper (one path); legacy visual workflow path retired.
                has_flow = (
                    "tenant_option_a_strip.html" in text
                    or "apple_class_visual_workflow_path.html" in text
                    or "world_class_guided_stepper.html" in text
                )
                self.assertTrue(has_flow, msg=f"{path.name} missing Option A / guided flow")
                self.assertIn("hide_nav_detail", text)
                self.assertIn("apple_class_dependency_graph.html", text)
                self.assertIn("rollback", text.lower())
