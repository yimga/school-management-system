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
        nav = (ROOT / "apps" / "platform_runtime" / "operational_center_nav.py").read_text(encoding="utf-8")
        for path in paths:
            text = f"{path.read_text(encoding='utf-8')}\n{nav}"
            with self.subTest(path=path.name):
                self.assertIn("data-apple-class-governed-installation", text)
                self.assertIn("apple_class_visual_workflow_path.html", text)
                self.assertIn("apple_class_dependency_graph.html", text)
                self.assertIn("rollback", text.lower())
