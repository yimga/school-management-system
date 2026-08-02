"""Contract seals for the 2026-08-02 finance dashboard band consolidation.

The finance home stacked FOUR bands that each restated the same
receivables/overdue KPIs and open-invoices/payment-readiness actions:

    masthead (build_masthead) · decision-engine surface (phase7_de) ·
    metric ticker (finance_metrics) · dashboard hero (hero)

`phase7_de` was in fact a LITERAL re-projection of `hero` — its metrics were
``hero["stats"][:4]`` and its next-actions ``hero["actions"][:3]`` (see the
pre-consolidation views_dashboard.py) — so the decision-engine band and the
hero band rendered the same stats and actions twice, and the ticker restated
the same numbers a third time.

The consolidation converges on the money-desk grammar (the same grammar the
view comment calls "platform billing"): ONE command band (masthead, with the
overdue / access-request chips + primary/secondary actions), ONE KPI row
(metric ticker), and the workflow action rail (which carries the
``data-task="money_center"`` step instrumentation + the "More money actions"
disclosure). The legacy generic hero and its decision-engine re-projection are
dropped, and their now-dead view computation (`hero`, `urgent_queue`,
`activity_rows`, `phase7_de`) is removed.

Two layers of proof:
  * render (TestCase) — the page still returns 200 and the two removed bands
    are absent from the rendered HTML while the kept bands + money_center JS
    wiring are present. Mirrors the proven RequestFactory harness in
    test_payment_readiness_dashboard.
  * source seal (SimpleTestCase, no DB) — the template no longer includes the
    two partials and the view no longer computes the dead context.
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.sessions.backends.db import SessionStore
from django.template.loader import get_template
from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.accounts.models import User
from apps.finance.models import ComplianceProfile
from apps.finance.regional_payment_profiles import clear_profile_cache
from apps.finance.views_dashboard import dashboard
from apps.schools.models import School


def _template_source(name: str) -> str:
    tpl = get_template(name)
    with open(tpl.origin.name, "r", encoding="utf-8") as fh:
        return fh.read()


class FinanceDashboardConsolidationRenderTests(TestCase):
    """The consolidated finance home renders 200 with the two duplicate bands gone."""

    def tearDown(self):
        clear_profile_cache()

    def setUp(self):
        self.school = School.objects.create(
            name="Tenant A",
            slug="tenant-a",
            subdomain="tenanta",
            is_active=True,
        )
        self.profile = ComplianceProfile.objects.create(
            name="CM Corridor",
            country_code="CM",
            currency_code="XAF",
            is_active=True,
        )
        # is_staff passes @require_permission("finance.view","finance.manage")
        # via user_has_permission (apps/accounts/decorators.py) — same signal the
        # sibling payment-readiness dashboard test relies on.
        self.staff = User.objects.create_user(
            username="financestaff",
            password="Pass_1234",
            email="finance@example.com",
            is_staff=True,
        )

    def _render(self):
        request = RequestFactory().get("/finance/")
        request.user = self.staff
        request.school = self.school
        request.session = SessionStore()  # RequestFactory has no session
        with patch(
            "apps.finance.views_dashboard._active_profile",
            return_value=self.profile,
        ):
            return dashboard(request)

    def test_dashboard_renders_200(self):
        self.assertEqual(self._render().status_code, 200)

    def test_removed_bands_absent(self):
        content = self._render().content.decode("utf-8")
        # The legacy generic hero band (widgets/dashboard_hero.html) is gone.
        # Assert the rendered band, not the bare word — match the section's class
        # attribute so this cannot be satisfied by an unrelated substring.
        self.assertNotIn('class="dashboard-hero', content)
        # Its literal re-projection, the decision-engine surface, is gone. NOTE:
        # css/decision-engine-surface.css legitimately stays loaded — it also
        # styles the surviving wcx rail's `.de-secondary-collapsible` disclosure
        # — so assert the SECTION's class, never the bare "decision-engine-surface"
        # substring (which the stylesheet href would otherwise match).
        self.assertNotIn('class="decision-engine-surface"', content)
        self.assertNotIn('data-decision-engine="surface"', content)

    def test_kept_bands_and_money_center_wiring_present(self):
        content = self._render().content.decode("utf-8")
        # ONE command band (masthead) survives.
        self.assertIn('data-rmc-page-masthead="1"', content)
        # The workflow action rail + its money_center task instrumentation survive.
        self.assertIn("rmc-wcx-action-rail", content)
        self.assertIn('data-task="money_center"', content)


class FinanceDashboardConsolidationSourceSealTests(SimpleTestCase):
    """Source-contract seals — fail on the pre-2026-08-02 template + view."""

    def setUp(self):
        self.tpl = _template_source("finance/dashboard.html")
        with open(
            "apps/finance/views_dashboard.py", "r", encoding="utf-8"
        ) as fh:
            self.view = fh.read()

    def test_duplicate_bands_removed_from_template(self):
        self.assertNotIn("components/decision_engine_surface.html", self.tpl)
        self.assertNotIn("widgets/dashboard_hero.html", self.tpl)
        self.assertNotIn("phase7_de", self.tpl)

    def test_kept_bands_preserved_in_template(self):
        self.assertIn("components/rmc_page_masthead.html", self.tpl)
        self.assertIn("components/rmc_metric_ticker.html", self.tpl)
        self.assertIn("rmc-wcx-action-rail", self.tpl)
        self.assertIn('data-task="money_center"', self.tpl)

    def test_dead_context_removed_from_view(self):
        self.assertNotIn("phase7_de", self.view)
        self.assertNotIn("hero = {", self.view)
        self.assertNotIn("urgent_queue", self.view)
        self.assertNotIn("activity_rows", self.view)

    def test_money_desk_grammar_preserved_in_view(self):
        # The kept KPI row + command band are still computed.
        self.assertIn("finance_metrics", self.view)
        self.assertIn("build_masthead", self.view)
