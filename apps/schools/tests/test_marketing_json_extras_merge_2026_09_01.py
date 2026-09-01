"""A JSON content file must OVERRIDE a page's extras, not replace them.

``config/marketing_content/<slug>.json`` carries copy -- label, headline,
segments. Extras (diagrams, data-viz, FAQs, SLA figures, trust strips, layout
flags) live in ``MARKETING_PAGE_EXTRAS``. ``_load_marketing_page_from_file``
returns ``data.get("extras")`` or ``{}``, and ``marketing_page`` took that
wholesale, so any slug whose JSON declares no extras rendered with none.

Measured on 2026-09-01: 23 slugs carry a MARKETING_PAGE_EXTRAS entry and every
one of them has a JSON file; 10 of those files declare no extras. Those ten
pages were the whole trust surface --

    /trust-center/   SLA figure, encryption copy, architecture summary,
                     integration trust categories, status URL, support summary
    /uptime/         uptime target, status URL
    /why-switch/     FAQs, and with them the FAQ JSON-LD, which is gated on
                     page_extras["faqs"]
    /products/analytics/, /platform/, /education-operating-system/
                     their diagram and data-viz

-- and the branch in ``marketing_page`` that reads
``page_extras.get("sla_uptime")`` for exactly trust-center and uptime could
never fire.

Found by three red tests in test_marketing_validation.py that had been carried
without a cause.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from django.test import Client, TestCase, override_settings

from apps.schools.marketing_page_definitions import MARKETING_PAGE_EXTRAS


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class MarketingJsonExtrasMergeTests(TestCase):
    """TestCase, not SimpleTestCase: the marketing views query while rendering

    (measured -- DatabaseOperationForbidden on every one of these pages).
    """
    host = "runmycampus.com"

    def setUp(self):
        self.client = Client()
        self.env = patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "",
            },
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def _get(self, path):
        resp = self.client.get(path, HTTP_HOST=self.host, follow=True)
        self.assertEqual(resp.status_code, 200, f"{path} -> {resp.status_code}")
        return resp

    def test_the_python_extras_survive_a_json_file_that_declares_none(self):
        """/products/analytics/ carries a data-viz in Python and none in JSON."""
        resp = self._get("/products/analytics/")
        self.assertContains(resp, "platform-diagram-marketing.svg")
        self.assertContains(resp, "Data intelligence loop")

    def test_the_uptime_figures_reach_the_page(self):
        """/uptime/ renders the SLA block that page_extras drives."""
        resp = self._get("/uptime/")
        self.assertContains(resp, "Uptime target")
        self.assertContains(resp, "99.9%")

    def test_the_sla_extras_reach_the_trust_center_context(self):
        """Asserted on the CONTEXT, not the page, and deliberately so.

        The bug is that page_extras arrived empty. /trust-center/ renders a
        different inner template from /uptime/ and does not show the SLA
        block; asserting it did would be claiming something this fix does
        not do. What the fix restores is the DATA -- including the branch in
        marketing_page that rewrites sla_uptime for exactly this slug and
        could not fire while page_extras was {}.
        """
        resp = self._get("/trust-center/")
        extras = resp.context["page_extras"]
        self.assertIn("sla_uptime", extras)
        self.assertEqual(extras["sla_uptime"]["uptime_target"], "99.9%")
        self.assertIn("encryption_copy", extras)
        self.assertIn("architecture_summary", extras)

    def test_the_faq_schema_reaches_why_switch(self):
        """FAQ JSON-LD is gated on page_extras['faqs'], which was being dropped."""
        resp = self._get("/why-switch/")
        self.assertContains(resp, "FAQPage")

    def test_a_json_extras_key_still_wins_over_the_python_one(self):
        """The mirror. A merge that let Python win would be its own regression.

        platform-analytics declares data_viz_path in BOTH places and they
        differ, so exactly one of them can be on the page.
        """
        python_value = MARKETING_PAGE_EXTRAS["platform-analytics"]["data_viz_path"]
        self.assertEqual(python_value, "images/marketing/viz-admin.svg")
        resp = self._get("/platform/analytics/")
        self.assertContains(resp, "platform-analytics-leadership.svg")
        self.assertNotContains(resp, "viz-admin.svg")
