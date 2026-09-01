from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_markup

ROOT = Path(__file__).resolve().parents[3]
_BACKEND_DASHBOARD = ROOT / "templates/accounts/backend_dashboard.html"
_SETUP_SURFACE = ROOT / "templates/partials/tenant/setup_command_surface.html"


class TenantLayoutBalanceCleanupContractTests(SimpleTestCase):
    def test_admin_shortcuts_are_preserved_and_have_balance_hook(self):
        template = (ROOT / "templates/accounts/backend_dashboard.html").read_text(
            encoding="utf-8"
        )
        # Every one of these labels is a {% trans %} msgid, so it is template code
        # and no parse or render of the file can see it: they stay source reads.
        for label in ("Configuration", "School Studio", "Configure hub", "Finance"):
            self.assertIn(label, template)
        # The balance hook itself IS markup. Reading it cannot tell a rendered
        # shortcut rail from one moved inside {% comment %} -- and a commented-out
        # rail is exactly the layout this contract exists to catch.
        assert_markup(self, _BACKEND_DASHBOARD, "rmc-admin-deep-links")

    def test_setup_choices_use_full_width_alignment_contract(self):
        css = (ROOT / "static/css/rmc-setup-surface.css").read_text(encoding="utf-8")
        required = (
            ".rmc-setup-surface__branch > .rmc-setup-surface__cards",
            "grid-template-columns: repeat(4, minmax(0, 1fr))",
            "grid-template-columns: repeat(2, minmax(0, 1fr))",
            "grid-template-columns: 1fr",
            "grid-template-columns: minmax(0, 1fr) auto",
            "justify-self: end",
            "text-align: end",
        )
        for token in required:
            self.assertIn(token, css)

    def test_cleanup_does_not_remove_setup_actions(self):
        template = (
            ROOT / "templates/partials/tenant/setup_command_surface.html"
        ).read_text(encoding="utf-8")
        # These four are template CODE -- two {{ }} variable paths and two context
        # names read by {% if %}/{% url %} -- so the source read is the only thing
        # that can see them.
        for token in (
            "choice.cta_url",
            "choice.cta_label",
            "rmc_setup_migration_flow",
            "rmc_setup_checklist_url",
        ):
            self.assertIn(token, template)
        # The CTA class is emitted text: ask the engine whether the surface still
        # renders the action it is named for.
        assert_markup(self, _SETUP_SURFACE, "rmc-setup-surface__card-cta")

