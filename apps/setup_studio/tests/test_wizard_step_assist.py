"""Per-step wizard AI assist wiring (no DB).

Locks the contract: the help rail exposes the assist hook + reuses the working
tenant copilot endpoint, and the wizard runner loads the assist JS/CSS.
"""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

_REPO = Path(__file__).resolve().parents[3]


class WizardStepAssistWiringTests(SimpleTestCase):
    def test_help_rail_exposes_assist_hook_and_reuses_endpoint(self):
        tpl = (_REPO / "templates" / "setup_studio" / "partials" / "wizard_help_rail.html").read_text(encoding="utf-8")
        self.assertIn("data-rmc-wizard-assist", tpl)
        # Reuses the working tenant copilot endpoint (no new endpoint).
        self.assertIn("portal:copilot_rail_send", tpl)
        # Safe `as` form so it no-ops on operator hosts.
        self.assertIn("as rmc_wizard_assist_endpoint", tpl)
        self.assertIn("data-step", tpl)

    def test_assist_endpoint_resolves_on_tenant_urlconf(self):
        """The assist depends on ``portal:copilot_rail_send`` resolving where the
        wizard actually renders — tenant hosts (config.tenant_urls). A refactor
        that drops the portal include from the tenant urlconf would silently kill
        the per-step AI assist (the ``as`` form fails soft to ""). Catch it here."""
        from django.urls import reverse

        url = reverse("portal:copilot_rail_send", urlconf="config.tenant_urls")
        self.assertIn("copilot/rail/send", url)

    def test_runner_loads_assist_assets(self):
        tpl = (_REPO / "templates" / "setup_studio" / "tenant_wizard.html").read_text(encoding="utf-8")
        self.assertIn("rmc-wizard-step-assist.js", tpl)
        self.assertIn("rmc-wizard-assist.css", tpl)
        # Script must carry the CSP nonce.
        self.assertRegex(tpl, r"rmc-wizard-step-assist\.js[^>]*nonce=")

    def test_assist_css_defines_referenced_classes(self):
        css = (_REPO / "static" / "css" / "rmc-wizard-assist.css").read_text(encoding="utf-8")
        for cls in (
            ".rmc-wizard-assist",
            ".rmc-wizard-assist__title",
            ".rmc-wizard-assist__hint",
            ".rmc-wizard-assist__form",
            ".rmc-wizard-assist__input",
            ".rmc-wizard-assist__send",
            ".rmc-wizard-assist__reply",
        ):
            self.assertIn(cls, css)
