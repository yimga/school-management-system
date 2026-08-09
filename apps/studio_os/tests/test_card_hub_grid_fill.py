"""Seal: platform card-hub grids use auto-FIT, not auto-fill (non-studio passes).

Companion to test_studio_cockpit_grid_fill.py. The recurring "everything is
left-oriented / pages too long" complaint is the CSS-grid `auto-fill` trap:
`repeat(auto-fill, minmax(N, 1fr))` reserves empty PHANTOM trailing tracks when
a row has fewer cards than fit, so the cards cluster against the left edge with
a wasted empty column on the right. `auto-fit` collapses those empty tracks so
the surviving cards stretch (via the `1fr`) to fill the canvas width.

This is the deliberate follow-up sweep of the ~45 auto-fill grids, taken one
scoped surface family at a time (NOT a blind find-replace — fixed-tile
galleries legitimately keep auto-fill). Grids sealed here are added family by
family as each pass ships.

  WIZARD family (tenant-facing setup / onboarding flows):
    .rmc-wz-grid, .rmc-wizard-index-grid, .rmc-wizard-zf-domain-grid, .ovendor-grid

  PORTAL family (tenant home / parent / teacher surfaces):
    .quick-actions-grid, .children-grid:not(.row), .rmc-preview-live-class-grid,
    .rmc-security-hub-grid
    (left as auto-fill on purpose: .rmc-social-moderation — an image-tile gallery
     where a lone tile stretched full-width would balloon the image.)

  MARKETING family (public platform pages / home): the six marketing-platform-*
    pages' .mkt-*-handoff-grid (block-link hubs) + .mkt-*-roles (role cards), plus
    .mkt-modules-grid / .mkt-ecosystem-grid in the shell and the tenant marketing
    home. All genuine link/card hubs (the sibling .mkt-platform-grid was already
    auto-fit — the house style); no fixed-tile image galleries among them. The
    minified marketing-enhanced.min.css is a build artifact and left untouched.

  ADMIN family (stable admin shells only — the peer's active /admin/ v16.x files
    cp-parity / approval-surface-v15 / django-canvas-contract, the shared .cp-catalog
    class, and the Unfold .bento-grid are deliberately NOT touched this pass):
    .admin-app-index__grid, .cp-admin-app-list, .backend-v2-action-grid,
    .rmc-admin-catalog-model-grid, .rmc-admin-mirror-grid
    (left as auto-fill on purpose: .backend-v2-chip-row — a pill/chip row where
     stretching rounded chips full-width reads wrong.)

  RESIDUALS (final QA sweep — hubs missed by the family passes):
    .rmc-wfp-flight-deck__run-grid, .rmc-mkt-catalog__grid, .hub-page .hub-cards,
    .rmc-kbd-cheatsheet__grid, and the tenant-dashboard .rmc-dh-cards /
    .rmc-dh-cards--wide / .rmc-dh-subj (source made honest; already auto-fit at
    runtime via rmc-kpi-grid-canonical.css's !important override).
    Remaining deliberate auto-fill galleries platform-wide: .rmc-seating-grid
    (fixed desk tiles), .rmc-lux-skeleton--grid-cell (loading placeholder),
    colour/token swatches, data-viz heat cells, day1 gradient-stop chips,
    social-moderation image tiles, and the peer-owned .cp-catalog / .bento-grid.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase

_CSS_DIR = Path(__file__).resolve().parents[3] / "static" / "css"
_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _rule_body(css: str, selector: str, *, occurrence: int = 0) -> str:
    """Return the nth `selector {...}` block with CSS comments stripped — the
    prose comments deliberately say "auto-fill", so assertions must inspect the
    real declarations, not the explanation."""
    needle = selector + " {"
    start = -1
    for _ in range(occurrence + 1):
        start = css.find(needle, start + 1)
        assert start != -1, f"selector {selector!r} (occurrence {occurrence}) not found"
    open_brace = css.find("{", start)
    close_brace = css.find("}", open_brace)
    return _COMMENT.sub("", css[open_brace + 1 : close_brace])


class WizardCardHubGridFillTest(SimpleTestCase):
    def _read(self, name: str) -> str:
        return (_CSS_DIR / name).read_text(encoding="utf-8")

    def _assert_auto_fit(self, css: str, selector: str, *, occurrence: int = 0):
        body = _rule_body(css, selector, occurrence=occurrence)
        self.assertIn("auto-fit", body, f"{selector} (occ {occurrence}) must be auto-fit")
        self.assertNotIn("auto-fill", body, f"{selector} (occ {occurrence}) still auto-fill")

    def test_wizard_engine_card_grid_is_auto_fit(self):
        self._assert_auto_fit(self._read("rmc-wizard-engine.css"), ".rmc-wz-grid")

    def test_wizard_index_card_grid_is_auto_fit(self):
        self._assert_auto_fit(self._read("rmc-wizard-index.css"), ".rmc-wizard-index-grid")

    def test_wizard_zf_domain_grid_is_auto_fit(self):
        self._assert_auto_fit(self._read("rmc-wizard.css"), ".rmc-wizard-zf-domain-grid")

    def test_onboarding_vendor_grid_is_auto_fit_below_desktop(self):
        css = self._read("onboarding-migration.css")
        # base + the >=576px override are the auto-fill sites we converted.
        self._assert_auto_fit(css, ".ovendor-grid", occurrence=0)
        self._assert_auto_fit(css, ".ovendor-grid", occurrence=1)

    def test_onboarding_vendor_grid_keeps_deliberate_4col_on_desktop(self):
        # The >=992px rule is a deliberate fixed 4-column cap (vendor tiles are a
        # small known set), NOT the auto-fill trap. Guard that the sweep did not
        # accidentally rewrite it.
        css = self._read("onboarding-migration.css")
        body = _rule_body(css, ".ovendor-grid", occurrence=2)
        self.assertIn("repeat(4,", body)


class PortalCardHubGridFillTest(SimpleTestCase):
    def _read(self, name: str) -> str:
        return (_CSS_DIR / name).read_text(encoding="utf-8")

    def _assert_auto_fit(self, css: str, selector: str, *, occurrence: int = 0):
        body = _rule_body(css, selector, occurrence=occurrence)
        self.assertIn("auto-fit", body, f"{selector} (occ {occurrence}) must be auto-fit")
        self.assertNotIn("auto-fill", body, f"{selector} (occ {occurrence}) still auto-fill")

    def test_quick_actions_grid_is_auto_fit_both_breakpoints(self):
        css = self._read("portal-ui-components.css")
        # base rule + the max-width:768px override
        self._assert_auto_fit(css, ".quick-actions-grid", occurrence=0)
        self._assert_auto_fit(css, ".quick-actions-grid", occurrence=1)

    def test_parent_children_grid_is_auto_fit(self):
        self._assert_auto_fit(
            self._read("phase2-portal-bundle.css"), ".children-grid:not(.row)"
        )

    def test_teacher_preview_class_grid_is_auto_fit(self):
        self._assert_auto_fit(
            self._read("rmc-tenant-preview-live-bridge.css"),
            ".rmc-preview-live-class-grid",
        )

    def test_security_hub_grid_is_auto_fit(self):
        self._assert_auto_fit(self._read("rmc-mfa-checkpoint.css"), ".rmc-security-hub-grid")

    def test_social_moderation_gallery_keeps_auto_fill_by_design(self):
        # Image-tile gallery: a lone tile stretched full-width would balloon the
        # image, so this deliberately keeps auto-fill. Guard against a blind sweep.
        body = _rule_body(self._read("rmc-social-feed.css"), ".rmc-social-moderation")
        self.assertIn("auto-fill", body)


class MarketingCardHubGridFillTest(SimpleTestCase):
    _MKT = _CSS_DIR.parent / "marketing" / "css"
    # (base_dir, filename, selector) for every marketing hub converted this pass.
    _HUBS = [
        (_MKT, "marketing-platform-admissions.css", ".mkt-adm-handoff-grid"),
        (_MKT, "marketing-platform-admissions.css", ".mkt-adm-roles"),
        (_MKT, "marketing-platform-analytics.css", ".mkt-analytics-handoff-grid"),
        (_MKT, "marketing-platform-analytics.css", ".mkt-analytics-roles"),
        (_MKT, "marketing-platform-fees-payments.css", ".mkt-fees-handoff-grid"),
        (_MKT, "marketing-platform-fees-payments.css", ".mkt-fees-roles"),
        (_MKT, "marketing-platform-parent-portal.css", ".mkt-parent-handoff-grid"),
        (_MKT, "marketing-platform-parent-portal.css", ".mkt-parent-roles"),
        (_MKT, "marketing-platform-security.css", ".mkt-security-handoff-grid"),
        (_MKT, "marketing-platform-security.css", ".mkt-security-roles"),
        (_MKT, "marketing-platform-teacher-portal.css", ".mkt-teacher-handoff-grid"),
        (_MKT, "marketing-platform-teacher-portal.css", ".mkt-teacher-roles"),
        (_MKT, "marketing-shell.css", ".marketing-home .mkt-modules-grid"),
        (_MKT, "marketing-shell.css", ".marketing-home .mkt-ecosystem-grid"),
        (_CSS_DIR, "marketing-home.css", ".marketing-home .mkt-modules-grid"),
        (_CSS_DIR, "marketing-home.css", ".marketing-home .mkt-ecosystem-grid"),
    ]

    def test_all_marketing_hubs_are_auto_fit(self):
        for base, name, selector in self._HUBS:
            css = (base / name).read_text(encoding="utf-8")
            body = _rule_body(css, selector)
            self.assertIn("auto-fit", body, f"{name} {selector} must be auto-fit")
            self.assertNotIn("auto-fill", body, f"{name} {selector} still auto-fill")


class AdminCardHubGridFillTest(SimpleTestCase):
    def _read(self, name: str) -> str:
        return (_CSS_DIR / name).read_text(encoding="utf-8")

    def _assert_auto_fit(self, css: str, selector: str):
        body = _rule_body(css, selector)
        self.assertIn("auto-fit", body, f"{selector} must be auto-fit")
        self.assertNotIn("auto-fill", body, f"{selector} still auto-fill")

    def test_admin_app_index_grids_are_auto_fit(self):
        css = self._read("phase2-admin-bundle.css")
        self._assert_auto_fit(css, ".admin-app-index__grid")
        self._assert_auto_fit(css, ".cp-admin-app-list")

    def test_backend_action_grid_is_auto_fit(self):
        self._assert_auto_fit(self._read("backend-dashboard-v2.css"), ".backend-v2-action-grid")

    def test_admin_catalog_model_grid_is_auto_fit(self):
        self._assert_auto_fit(
            self._read("admin-platform-catalog.css"), ".rmc-admin-catalog-model-grid"
        )

    def test_admin_mirror_grid_is_auto_fit(self):
        self._assert_auto_fit(self._read("rmc-admin-mirror.css"), ".rmc-admin-mirror-grid")

    def test_backend_chip_row_keeps_auto_fill_by_design(self):
        # Pill/chip row: stretching rounded chips full-width reads wrong, so this
        # deliberately keeps auto-fill. Guard against a blind sweep.
        body = _rule_body(self._read("backend-dashboard-v2.css"), ".backend-v2-chip-row")
        self.assertIn("auto-fill", body)


class ResidualCardHubGridFillTest(SimpleTestCase):
    """Final QA sweep: residual hubs the family passes missed, the tenant-dashboard
    source honesty fix, and the two remaining deliberate galleries."""

    def _read(self, name: str) -> str:
        return (_CSS_DIR / name).read_text(encoding="utf-8")

    def _assert_auto_fit(self, name: str, selector: str):
        body = _rule_body(self._read(name), selector)
        self.assertIn("auto-fit", body, f"{name} {selector} must be auto-fit")
        self.assertNotIn("auto-fill", body, f"{name} {selector} still auto-fill")

    def test_residual_hubs_are_auto_fit(self):
        self._assert_auto_fit("rmc-workflow-flight-deck.css", ".rmc-wfp-flight-deck__run-grid")
        self._assert_auto_fit("marketplace-app-catalog.css", ".rmc-mkt-catalog__grid")
        self._assert_auto_fit("hub-premium.css", ".hub-page .hub-cards")
        self._assert_auto_fit("design-tokens.css", ".rmc-kbd-cheatsheet__grid")

    def test_tenant_dashboard_hub_grids_are_auto_fit(self):
        css = self._read("rmc-tenant-dashboard-100x.css")
        for sel in (".rmc-dh-cards", ".rmc-dh-cards--wide", ".rmc-dh-subj"):
            body = _rule_body(css, sel)
            self.assertIn("auto-fit", body, f"{sel} must be auto-fit")
            self.assertNotIn("auto-fill", body, f"{sel} still auto-fill")

    def test_seating_and_skeleton_keep_auto_fill_by_design(self):
        # Seating chart = fixed-size desk tiles (a short last row must not balloon);
        # skeleton = transient loading placeholder. Both correctly keep auto-fill.
        seating = _rule_body(self._read("rmc-class-grammar.css"), ".rmc-seating-grid")
        self.assertIn("auto-fill", seating)
        skel = _rule_body(self._read("lux-workspace.css"), ".rmc-lux-skeleton--grid-cell")
        self.assertIn("auto-fill", skel)


class PeerAdminCatalogGridFillTest(SimpleTestCase):
    """The /admin/ control-plane catalog surfaces: the shared .cp-catalog (styled
    across three files incl. an !important discover override), the Unfold
    .bento-grid, and the cp-parity catalog-model grid. These live in the peer's
    active v16.x territory and were taken as the FINAL pass once that work settled
    — every one of these files must now be free of the auto-fill left-cluster."""

    _FILES = [
        "rmc-admin-v1-200x.css",
        "admin-platform-catalog.css",
        "rmc-admin-approval-surface-v15.css",
        "admin-200x-shell-overlay.css",
        "admin-cp-parity.css",
    ]

    def test_admin_catalog_surfaces_have_no_auto_fill_grid(self):
        for name in self._FILES:
            css = (_CSS_DIR / name).read_text(encoding="utf-8")
            self.assertNotIn(
                "repeat(auto-fill",
                css,
                f"{name} reintroduced an auto-fill grid — catalog surfaces must fill the canvas",
            )
