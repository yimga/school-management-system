"""Seal: tenant-facing status badges use the platform's soft, theme-aware
grammar — never the harsh solid Bootstrap contextual badge (`text-bg-warning`
= bright #ffc107 yellow, `text-bg-success` = loud green, etc.).

Why this exists (recurring user complaint): the studio_os Launch page rendered
its "N% ready" health pill via `_mode_hero.html` as `badge text-bg-warning
text-dark` — the loud yellow the user repeatedly flagged as "not friendly for
the eyes" and out of sync with the rest of the platform. The reference surface
(the Launch-readiness embed) uses the token-based `rmc-badge rmc-badge--warning`
(a 12%-tint of `--status-warning`, theme-aware) and the Bootstrap SUBTLE
grammar (`bg-warning-subtle text-warning-emphasis border border-warning-subtle`,
which flips light/dark via `--bs-warning-*`). This wave standardised every
tenant-facing status badge onto that soft grammar.

Two independent seals:
  1. RENDER the mode-hero and assert the health pill emits the soft token badge,
     NOT `text-bg-warning`/`text-dark`. (Fails before the fix.)
  2. SOURCE-seal the full swept tenant-facing set against reintroducing any
     solid `text-bg-<color>` (or the invalid `text-bg-*-subtle` non-class that
     rendered transparent). Operator (`super_*`), Django `admin/`, the operator
     cockpit login preview, and the deliberate safeguarding "Urgent" red badge
     are intentionally out of scope and NOT listed here.
"""

import re
from pathlib import Path

from django.template.loader import render_to_string
from django.test import SimpleTestCase

_TEMPLATES = Path(__file__).resolve().parents[3] / "templates"

# Any solid Bootstrap contextual badge (`text-bg-success` … `text-bg-dark`) OR
# the invalid `text-bg-*-subtle` pseudo-class (not a real Bootstrap utility —
# renders as a bare, background-less badge).
_HARSH_BADGE = re.compile(r"text-bg-\w+")


class ModeHeroHealthPillPaletteTest(SimpleTestCase):
    def _render(self, status: str) -> str:
        return render_to_string(
            "studio_os/partials/_mode_hero.html",
            {
                "mode_label": "Launch",
                "mode_purpose": "Plan, role-preview, and infrastructure for going live.",
                "mode_health_label": "55% ready",
                "mode_health_status": status,
            },
        )

    def test_warn_health_uses_soft_token_badge_not_bootstrap_yellow(self):
        html = self._render("warn")
        self.assertIn("rmc-badge--warning", html)
        self.assertNotIn("text-bg-warning", html)
        # the old harsh pill forced dark text on the bright yellow
        self.assertNotIn("text-dark", html)

    def test_ok_health_uses_soft_token_success(self):
        html = self._render("ok")
        self.assertIn("rmc-badge--success", html)
        self.assertNotIn("text-bg-success", html)

    def test_bad_health_uses_soft_token_danger(self):
        html = self._render("bad")
        self.assertIn("rmc-badge--danger", html)
        self.assertNotIn("text-bg-danger", html)

    def test_unknown_health_falls_back_to_muted_not_secondary_solid(self):
        html = self._render("")
        self.assertIn("rmc-badge--muted", html)
        self.assertNotIn("text-bg-secondary", html)


class TenantSurfaceBadgePaletteSourceSeal(SimpleTestCase):
    """Every tenant-facing surface swept this wave must stay free of the harsh
    solid / invalid-subtle Bootstrap contextual badge."""

    # Repo-relative template paths (POSIX) swept to the soft grammar.
    _SWEPT = [
        "studio_os/partials/_mode_hero.html",
        "studio_os/partials/launch_studio_overview_body.html",
        "studio_os/shell.html",
        "studio_os/partials/shell_main_content.html",
        "components/rmc_os_status_strip.html",
        "components/rmc_os_page_header.html",
        "components/rmc_page_masthead.html",
        "platform_runtime/tenant_blueprint_setup.html",
        "platform_runtime/school_configuration_center.html",
        "customersuccess/guided_onboarding.html",
        "siteconfig/partials/theme_colors_content.html",
        "siteconfig/partials/theme_colors_page_body.html",
        "accounts/tenant_join_codes.html",
        "accounts/sso_connections.html",
        "academics/hub.html",
        "schoolops/ops_inventory.html",
        "reports/bulk_console.html",
        "schools/partials/data_residency_readiness_panel.html",
        "marketplace/partials/app_catalog_card.html",
    ]

    def test_no_harsh_or_invalid_contextual_badge_remains(self):
        for rel in self._SWEPT:
            source = (_TEMPLATES / rel).read_text(encoding="utf-8")
            hits = _HARSH_BADGE.findall(source)
            self.assertEqual(
                [],
                hits,
                f"{rel} still uses solid/invalid Bootstrap badge(s) {hits} — "
                "use the soft theme-aware grammar "
                "(bg-<c>-subtle text-<c>-emphasis border border-<c>-subtle "
                "or rmc-badge rmc-badge--<c>).",
            )

    def test_swept_surfaces_declare_the_soft_grammar(self):
        # Belt-and-suspenders: the swept files that carry status badges should
        # now reference the subtle grammar (or rmc-badge for the hero), proving
        # the replacement landed rather than the badge simply being deleted.
        for rel in self._SWEPT:
            source = (_TEMPLATES / rel).read_text(encoding="utf-8")
            self.assertTrue(
                ("-subtle" in source) or ("rmc-badge--" in source),
                f"{rel} lost its soft badge grammar entirely",
            )
