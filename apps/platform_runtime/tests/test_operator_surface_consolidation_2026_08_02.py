"""
Contract seals for the 2026-08-02 operator/config surface de-fluff wave.

These are the same class of "read the template source and assert the consolidated
structure" regression seals used for the Admin Home cockpit. Each assertion is
MUST-FIRE: it would fail on the pre-2026-08-02 templates (raw stacked Bootstrap
cards, a card wrapping a lone button, a duplicate product-config link card) and
passes only once the surface is converged onto the bounded operator grammar.

No DB required (SimpleTestCase) — the templates are read via Django's own loader
so the check tracks whichever file the engine actually resolves.
"""

from __future__ import annotations

from django.template.loader import get_template
from django.test import SimpleTestCase


def _template_source(name: str) -> str:
    """Return the on-disk source of a template as the engine resolves it."""
    tpl = get_template(name)
    origin = tpl.origin.name
    with open(origin, "r", encoding="utf-8") as fh:
        return fh.read()


class ImplementationCommandCenterConsolidationTests(SimpleTestCase):
    TEMPLATE = "platform_runtime/implementation_command_center.html"

    def setUp(self):
        self.src = _template_source(self.TEMPLATE)

    def test_adopts_bounded_cp_panel_grammar(self):
        self.assertIn("cp-panel", self.src)
        self.assertIn("cp-panel-header", self.src)

    def test_no_raw_bootstrap_cards_remain(self):
        # The three stacked `card border-0 shadow-sm` boxes are gone.
        self.assertNotIn("card border-0 shadow-sm", self.src)

    def test_primary_next_action_folded_into_readiness_panel(self):
        # The lone-button "Primary next action" card is gone; the action now
        # lives in the readiness panel's header-actions zone.
        self.assertNotIn("Primary next action", self.src)
        self.assertIn("cp-panel-header-actions", self.src)
        self.assertIn("primary_next_action.url", self.src)

    def test_row_detail_table_wiring_preserved(self):
        # The genuinely-distinct adoption checklist table (and its drawer wiring)
        # survives the consolidation.
        self.assertIn('data-rmc-row-detail-table="1"', self.src)
        self.assertIn("portal_row_detail_drawer_bundle.html", self.src)


class TenantLifecycleDashboardConsolidationTests(SimpleTestCase):
    TEMPLATE = "platform_runtime/tenant_lifecycle_dashboard.html"

    def setUp(self):
        self.src = _template_source(self.TEMPLATE)

    def test_adopts_bounded_cp_panel_grammar(self):
        self.assertIn("cp-panel", self.src)
        self.assertIn("cp-panel-title", self.src)

    def test_portfolio_metrics_use_overview_tiles(self):
        # The portfolio-activation dl became a bounded cp-overview-grid of KPI tiles.
        self.assertIn("cp-overview-grid", self.src)
        self.assertIn("cp-overview-card", self.src)

    def test_no_raw_bootstrap_cards_remain(self):
        self.assertNotIn("card border-0 shadow-sm", self.src)

    def test_row_primary_action_wiring_preserved(self):
        # Task-tracking data attributes on the at-risk / expansion row actions survive.
        self.assertIn('data-task="tenant_lifecycle"', self.src)
        self.assertIn("lifecycle:at-risk-primary", self.src)
        self.assertIn("lifecycle:expansion-primary", self.src)


class TenantRuntimeConfigHubDedupeTests(SimpleTestCase):
    TEMPLATE = "siteconfig/partials/tenant_runtime_configuration_hub_body.html"

    def setUp(self):
        self.src = _template_source(self.TEMPLATE)

    def test_duplicate_product_links_card_removed(self):
        # The standalone "Product configuration links" card duplicated the
        # cp-evidence related-links bar; it is gone.
        self.assertNotIn("Product configuration links", self.src)

    def test_unique_product_links_folded_into_related_bar(self):
        # Nothing lost: the three links unique to the deleted card now live in
        # the single related-links bar.
        for label in ("Theme & colors", "School theme", "User preferences"):
            self.assertIn(label, self.src)

    def test_related_bar_still_canonical_link_surface(self):
        self.assertIn("cp-evidence-related", self.src)
