from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_markup


class PlatformActionContractTests(SimpleTestCase):
    def read(self, relative):
        return (Path(settings.BASE_DIR) / relative).read_text(encoding="utf-8")

    def test_every_authenticated_shell_loads_action_contract(self):
        for template in ("templates/base.html", "templates/portal_base.html", "templates/control_plane_base.html", "templates/admin/base_site.html"):
            with self.subTest(template=template):
                self.assertIn("css/rmc-action-contract.css", self.read(template))

    def test_generic_card_links_exclude_button_anchors(self):
        css = self.read("static/css/rmc-world-class-experience.css")
        self.assertIn(".card a:not(.btn):not(.cp-btn)", css)

    def test_contract_protects_card_actions_and_keyboard_focus(self):
        css = self.read("static/css/rmc-action-contract.css")
        self.assertIn("a.btn", css)
        self.assertIn("a.cp-btn", css)
        self.assertIn(":focus-visible", css)
        self.assertIn("@media (pointer: coarse)", css)


class Tenant360SupportContractTests(SimpleTestCase):
    def test_tenant_360_exposes_safe_effective_configuration(self):
        root = Path(settings.BASE_DIR)
        view = (root / "apps/schools/super_views_platform_monitoring.py").read_text(encoding="utf-8")
        tenant_360 = root / "templates/schools/super_tenant_360.html"
        template = tenant_360.read_text(encoding="utf-8")
        self.assertIn("support_configuration", view)
        self.assertIn("sensitive_fragments", view)
        # The disclosure sentence is a {% trans %} msgid -- template code, so it
        # stays a source read.
        self.assertIn("Credentials and secret-like values are always excluded", template)
        # "Exposes" is a claim about the page. The section id is emitted text, so
        # ask the engine rather than the bytes: a {% comment %} keeps the id and
        # renders no configuration panel at all.
        assert_markup(self, tenant_360, 'id="tenant-360-configuration"')
