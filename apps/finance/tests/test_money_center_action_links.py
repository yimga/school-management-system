"""The Money Center action rail must not ship a button that goes nowhere.

Django resolves an unknown variable to "" and renders href="", which a browser
treats as "this page". Such a button looks live, takes keyboard focus, has an
accessible name, and does nothing -- and nothing in the suite noticed, because
the template is valid and the view under test is the one that RENDERS the page,
not the one that was supposed to supply the variable.

That is what happened here: 6a155f984 removed the operational-frame include and
the context that fed it, leaving two anchors behind on
templates/finance/dashboard.html --

    href="{{ wcx_payment_readiness_url }}"    "Payment readiness"
    href="{{ wcx_workforce_money_url }}"      "Workforce & money hub"

-- with neither name set anywhere in apps/ or config/.

These assertions are made through the template ENGINE, so a dashboard whose
body is one {% comment %} fails them rather than passing on the strings still
sitting in its bytes.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_urls_reverse, url_names

ROOT = Path(__file__).resolve().parents[3]
DASHBOARD = ROOT / "templates" / "finance" / "dashboard.html"

# The primary rail, not the whole page: a data table legitimately builds hrefs
# from row objects, and demanding {% url %} there would be wrong.
ACTION_RAIL = re.compile(
    r'<div class="rmc-wcx-actions">(.*?)</div>', re.S
)


class MoneyCenterActionLinkTests(SimpleTestCase):
    def test_action_rail_builds_every_href_from_a_route(self):
        # The rail check itself has to read the SOURCE -- whether an href is a
        # bare variable is a fact about the text, not about any parse node. So
        # this pairs it with a parse-level assertion; without that the test
        # passes over a dashboard whose whole body is one {% comment %}, which
        # is exactly the vacuity being burned down elsewhere. Measured: the
        # first draft of this test WAS vacuous and the harness caught it.
        self.assertTrue(
            url_names(DASHBOARD), "the dashboard parses to no routes at all"
        )
        rail = ACTION_RAIL.search(DASHBOARD.read_text(encoding="utf-8"))
        self.assertIsNotNone(rail, "the Money Center action rail is gone")
        block = rail.group(1)
        self.assertIn("{% url ", block, "the rail routes nowhere at all")
        dangling = re.findall(r'href="\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}"', block)
        self.assertEqual(
            dangling,
            [],
            "Money Center action buttons whose href is a bare variable: "
            + ", ".join(dangling)
            + ". Django renders an unset variable as href='', which is a button "
            "that does nothing. Use {% url %}.",
        )

    def test_every_route_the_dashboard_names_still_exists(self):
        assert_urls_reverse(self, DASHBOARD)

    def test_the_two_repaired_buttons_route_where_their_labels_say(self):
        names = {name for name, _argc in url_names(DASHBOARD)}
        self.assertIn("finance:payment_readiness_dashboard", names)
        self.assertIn("finance:workforce_command_center", names)
