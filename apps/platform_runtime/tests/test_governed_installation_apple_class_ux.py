from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import (
    assert_markup,
    assert_wires,
)

_TN_ROOT = Path(__file__).resolve().parents[3]


ROOT = Path(__file__).resolve().parents[3]


class GovernedInstallationAppleClassTests(SimpleTestCase):
    def test_governed_surfaces_show_visual_flow_and_dependencies(self):
        paths = [
            ROOT / "templates" / "platform_runtime" / "change_requests.html",
            ROOT / "templates" / "platform_runtime" / "blueprint_marketplace.html",
            ROOT / "templates" / "platform_runtime" / "pack_marketplace.html",
        ]
        frame = (ROOT / "templates" / "components" / "rmc_operational_center_frame_inner.html").read_text(
            encoding="utf-8"
        )
        nav = (ROOT / "apps" / "platform_runtime" / "operational_center_nav.py").read_text(encoding="utf-8")
        for path in paths:
            text = f"{path.read_text(encoding='utf-8')}\n{nav}\n{frame}"
            with self.subTest(path=path.name):
                self.assertIn("data-apple-class-governed-installation", text)
                # MAX Wave 5: shared masthead via operational frame (Option-A wall purged).
                self.assertIn("rmc_operational_center_frame.html", path.read_text(encoding="utf-8"))
                self.assertIn("rmc_page_masthead.html", frame)
                self.assertIn("hide_nav_detail", text)
                self.assertIn("apple_class_dependency_graph.html", text)
                self.assertIn("rollback", text.lower())
        # The sweep above runs over a CONCATENATION of the page, the nav module
        # and the frame, so a hit says nothing about which file carries it.
        assert_wires(self, _TN_ROOT / "templates/platform_runtime/change_requests.html",
                     "rmc_operational_center_frame.html")
        assert_markup(self, _TN_ROOT / "templates/platform_runtime/change_requests.html",
                      "rmc-configuration-change-requests")
