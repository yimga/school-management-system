"""Console/Configure shell switcher is operator-hub gated (2026-07-27).

The workspace-mode switcher toggles into operator surfaces (Console = everyday
running, Configure = settings/branding/blueprint). It used to render for every
authenticated tenant user — parents/students included — who would only hit a
permission wall. It now self-gates on tenant_operator_hub_eligible, the same
signal the operator console strip uses.
"""

from __future__ import annotations

from unittest import mock

from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase, override_settings


@override_settings(ROOT_URLCONF="config.tenant_urls")
class ShellSwitcherRbacTests(SimpleTestCase):
    def _render(self, *, eligible: bool) -> str:
        req = RequestFactory().get("/portal/")
        req.user = mock.Mock(is_authenticated=True)
        tpl = Template("{% include 'components/rmc_shell_switcher.html' %}")
        # The filter imports tenant_operator_hub_eligible at call time.
        with mock.patch(
            "apps.accounts.permissions.tenant_operator_hub_eligible",
            return_value=eligible,
        ):
            return tpl.render(Context({"request": req}))

    def test_operator_eligible_user_sees_switcher(self):
        html = self._render(eligible=True)
        self.assertIn("rmc-shell-switcher", html)
        self.assertIn("Configure", html)
        self.assertIn("Console", html)

    def test_non_operator_user_does_not_see_switcher(self):
        html = self._render(eligible=False)
        self.assertNotIn("rmc-shell-switcher", html)
        self.assertNotIn("Configure", html)
