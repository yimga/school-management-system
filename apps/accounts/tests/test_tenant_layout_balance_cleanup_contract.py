from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class TenantLayoutBalanceCleanupContractTests(SimpleTestCase):
    def test_admin_shortcuts_are_preserved_and_have_balance_hook(self):
        template = (ROOT / "templates/accounts/backend_dashboard.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("rmc-admin-deep-links", template)
        for label in ("Configuration", "School Studio", "Configure hub", "Finance"):
            self.assertIn(label, template)

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
        for token in (
            "choice.cta_url",
            "choice.cta_label",
            "rmc_setup_migration_flow",
            "rmc-setup-surface__card-cta",
            "rmc_setup_checklist_url",
        ):
            self.assertIn(token, template)

