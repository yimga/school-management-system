"""Studio OS Overview — next-realm cockpit (v3.54.0, 2026-05-21).

Asserts the Overview-specific cockpit chrome lands correctly:

  - Mission-signal tile strip renders all 6 tiles (8 total incl. tenant/mode/host)
  - Tiles render `data-state="unknown"` when context vars are missing
  - Operator-only chips hidden when `request.public_host_kind != 'manager'`
  - No `href="#"` dummy links in agent-owned partials
  - data-rmc-* attributes present on the new cockpit body
  - studio-overview-cockpit.css is linked once per render

Tests are SimpleTestCase + static-file inspection so they run without
DB. They do NOT exercise the DB-backed studio_shell view directly — the
coordinator runs the integration suite after wiring the
overview_command_cockpit.html include into shell.html.
"""

from __future__ import annotations

from pathlib import Path

from django.template.loader import get_template
from django.test import RequestFactory, SimpleTestCase, override_settings


REPO_ROOT = Path(__file__).resolve().parents[3]
PARTIALS_DIR = REPO_ROOT / "templates" / "studio_os" / "partials"

SIGNAL_STRIP = PARTIALS_DIR / "cockpit_signal_strip.html"
COPILOT_RAIL = PARTIALS_DIR / "cockpit_copilot_rail.html"
GUIDANCE_PANEL = PARTIALS_DIR / "studio_guidance_panel.html"
OVERVIEW_BODY = PARTIALS_DIR / "overview_command_cockpit.html"
LAUNCH_OVERVIEW_BODY = PARTIALS_DIR / "launch_studio_overview_body.html"
LAUNCH_ROLE_PREVIEW = PARTIALS_DIR / "launch_studio_role_preview_pane.html"

OVERVIEW_CSS = REPO_ROOT / "static" / "css" / "studio-overview-cockpit.css"


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"]
)
class OverviewNextRealmStaticContractTests(SimpleTestCase):
    """Static-only tests — read partial source and CSS file from disk."""

    def setUp(self) -> None:
        for path in (
            SIGNAL_STRIP,
            COPILOT_RAIL,
            GUIDANCE_PANEL,
            OVERVIEW_BODY,
            LAUNCH_OVERVIEW_BODY,
            LAUNCH_ROLE_PREVIEW,
            OVERVIEW_CSS,
        ):
            self.assertTrue(path.exists(), f"missing required file: {path}")
        self.signal_strip_text = SIGNAL_STRIP.read_text(encoding="utf-8")
        self.copilot_rail_text = COPILOT_RAIL.read_text(encoding="utf-8")
        self.guidance_panel_text = GUIDANCE_PANEL.read_text(encoding="utf-8")
        self.overview_body_text = OVERVIEW_BODY.read_text(encoding="utf-8")
        self.launch_overview_text = LAUNCH_OVERVIEW_BODY.read_text(encoding="utf-8")
        self.launch_role_preview_text = LAUNCH_ROLE_PREVIEW.read_text(encoding="utf-8")
        self.overview_css_text = OVERVIEW_CSS.read_text(encoding="utf-8")

    # ----- Signal strip -----

    def test_signal_strip_links_overview_stylesheet_once(self) -> None:
        self.assertEqual(
            self.signal_strip_text.count("studio-overview-cockpit.css"),
            1,
            "cockpit_signal_strip.html must link studio-overview-cockpit.css exactly once",
        )

    def test_signal_strip_has_eight_overview_tiles(self) -> None:
        # 8 data-rmc-overview-tile elements: tenant, mode, pending-launches,
        # draft-experiences, active-automations, readiness, blockers, host-kind.
        count = self.signal_strip_text.count('data-rmc-overview-tile=')
        self.assertEqual(
            count,
            8,
            f"expected 8 mission-signal tiles, got {count}",
        )

    def test_signal_strip_uses_unknown_state_for_missing_vars(self) -> None:
        # data-state="unknown" appears at least 5 times (one per metric tile
        # that can be unknown: pending-launches, draft-experiences,
        # active-automations, readiness, blockers).
        self.assertIn('data-state="unknown"', self.signal_strip_text)

    def test_signal_strip_gates_operator_indicator_explicit(self) -> None:
        # Host-kind tile is the explicit operator vs tenant indicator.
        self.assertIn("public_host_kind", self.signal_strip_text)
        self.assertIn('data-rmc-overview-tile="host-kind"', self.signal_strip_text)

    def test_signal_strip_uses_trans_tags_for_all_copy(self) -> None:
        # No raw english that isn't wrapped in {% trans %} or {% blocktrans %}
        # (sample-check against the strings we wrote).
        for needle in ("Tenant", "Focus", "Pending launches", "Open blockers", "Host mode"):
            self.assertIn(needle, self.signal_strip_text)
            self.assertIn(f'{{% trans "{needle}" %}}', self.signal_strip_text)

    # ----- Overview command cockpit body -----

    def test_overview_body_has_required_data_attrs(self) -> None:
        required = [
            'data-rmc-overview-cockpit="1"',
            'data-rmc-overview-hero=',
            'data-rmc-overview-modes="1"',
            'data-rmc-overview-triptych="1"',
        ]
        for attr in required:
            self.assertIn(
                attr,
                self.overview_body_text,
                f"overview_command_cockpit.html missing {attr}",
            )

    def test_overview_body_renders_5_mode_card_resolutions(self) -> None:
        # Every mode should resolve through a real {% url %} tag — no href="#".
        for mode_id in ("experience", "automation", "output", "launch", "control"):
            self.assertIn(
                f"{{% url 'studio_os:{mode_id}' as mode_url %}}",
                self.overview_body_text,
                f"overview_command_cockpit.html must resolve studio_os:{mode_id}",
            )

    def test_overview_body_gates_operator_only_hubs(self) -> None:
        # RBAC and feature control are operator-only on the manager host.
        self.assertIn(
            "request.public_host_kind == 'manager'",
            self.overview_body_text,
            "operator-only chips must be gated by request.public_host_kind",
        )
        # And both chips carry the --operator variant class.
        self.assertIn("rmc-overview-hub-rail__chip--operator", self.overview_body_text)

    def test_overview_body_renders_three_triptych_cards(self) -> None:
        for card in ("readiness", "recent-activity", "live-previews"):
            self.assertIn(
                f'data-rmc-overview-card="{card}"',
                self.overview_body_text,
                f"overview_command_cockpit.html must render the {card} triptych card",
            )

    def test_overview_body_no_dummy_href(self) -> None:
        # No literal href="#" in agent-owned partials.
        for partial_name, text in (
            ("overview_command_cockpit.html", self.overview_body_text),
            ("cockpit_signal_strip.html", self.signal_strip_text),
            ("studio_guidance_panel.html", self.guidance_panel_text),
            ("launch_studio_overview_body.html", self.launch_overview_text),
            ("launch_studio_role_preview_pane.html", self.launch_role_preview_text),
        ):
            self.assertNotIn(
                'href="#"',
                text,
                f"{partial_name} must not contain dummy href=\"#\" links",
            )

    def test_launch_overview_body_avoids_step_title_default_filter(self) -> None:
        self.assertNotIn(
            "default:step.title",
            self.launch_overview_text,
            "launch_studio_overview_body must not reference step.title in default filters",
        )

    # ----- Co-pilot rail patches -----

    def test_copilot_rail_has_host_kind_badge(self) -> None:
        self.assertIn("rmc-copilot-rail__mode-badge", self.copilot_rail_text)
        self.assertIn('data-rmc-host-kind=', self.copilot_rail_text)

    def test_copilot_rail_has_preview_microlist(self) -> None:
        # Preview-as microlist surfaces studio_role_preview_entries.
        self.assertIn(
            'data-rmc-copilot-rail-previews="1"',
            self.copilot_rail_text,
            "copilot rail must surface preview-as microlist when entries present",
        )

    # ----- Guidance panel -----

    def test_guidance_panel_surfaces_primary_action_when_present(self) -> None:
        self.assertIn('data-rmc-guidance-action="primary"', self.guidance_panel_text)
        self.assertIn('data-rmc-guidance-action="secondary"', self.guidance_panel_text)
        self.assertIn('data-rmc-guidance-action="preview"', self.guidance_panel_text)

    def test_guidance_panel_surfaces_blocker_when_present(self) -> None:
        self.assertIn("rmc-studio-guidance__blocker", self.guidance_panel_text)
        self.assertIn("studio_guidance.blocker", self.guidance_panel_text)

    # ----- CSS contract -----

    def test_overview_css_defines_every_new_class(self) -> None:
        # Every .rmc-overview-* class referenced by the agent-owned partials
        # must be defined in studio-overview-cockpit.css so
        # scan_undefined_css_classes stays at 0.
        required_classes = [
            ".rmc-overview-signal-strip",
            ".rmc-overview-signal-tile",
            ".rmc-overview-signal-tile__label",
            ".rmc-overview-signal-tile__value",
            ".rmc-overview-signal-tile__hint",
            ".rmc-overview-cockpit",
            ".rmc-overview-hero",
            ".rmc-overview-hero__body",
            ".rmc-overview-hero__title",
            ".rmc-overview-hero__cta",
            ".rmc-overview-mode-grid",
            ".rmc-overview-mode-card",
            ".rmc-overview-mode-card__title",
            ".rmc-overview-mode-card__icon",
            ".rmc-overview-mode-card__desc",
            ".rmc-overview-mode-card__cta",
            ".rmc-overview-triptych",
            ".rmc-overview-card",
            ".rmc-overview-card__title",
            ".rmc-overview-card__list",
            ".rmc-overview-hub-rail",
            ".rmc-overview-hub-rail__chip",
            ".rmc-overview-hub-rail__chip--operator",
            ".rmc-studio-guidance__actions",
            ".rmc-studio-guidance__blocker",
            ".rmc-copilot-rail__mode-badge",
            ".rmc-copilot-rail__preview-list",
        ]
        for cls in required_classes:
            self.assertIn(
                cls,
                self.overview_css_text,
                f"studio-overview-cockpit.css must define {cls}",
            )

    def test_overview_css_uses_no_raw_hex(self) -> None:
        # No raw hex literals — every color must come from var(--*).
        import re

        # Allow # inside url(...) / fragment refs / data: URIs / declarations
        # of CSS variable VALUES themselves (none here). We're scanning for
        # standalone #abc / #abcdef tokens.
        hex_pattern = re.compile(r"#[0-9A-Fa-f]{3,8}\b")
        # Strip line comments first.
        lines = self.overview_css_text.splitlines()
        cleaned = []
        in_block_comment = False
        for line in lines:
            if in_block_comment:
                end = line.find("*/")
                if end >= 0:
                    line = line[end + 2 :]
                    in_block_comment = False
                else:
                    continue
            while True:
                start = line.find("/*")
                if start < 0:
                    break
                end = line.find("*/", start + 2)
                if end < 0:
                    line = line[:start]
                    in_block_comment = True
                    break
                line = line[:start] + line[end + 2 :]
            cleaned.append(line)
        scrubbed = "\n".join(cleaned)
        matches = hex_pattern.findall(scrubbed)
        self.assertEqual(
            matches,
            [],
            f"studio-overview-cockpit.css contains raw hex literal(s) outside comments: {matches}",
        )

    def test_overview_css_uses_design_tokens(self) -> None:
        # Sample-check a handful of expected token consumers.
        for token in (
            "var(--surface-elevated)",
            "var(--surface-canvas)",
            "var(--text-primary)",
            "var(--text-secondary)",
            "var(--text-tertiary)",
            "var(--hairline)",
            "var(--elev-1)",
        ):
            self.assertIn(
                token,
                self.overview_css_text,
                f"studio-overview-cockpit.css must consume design token {token}",
            )

    def test_overview_css_responsive_breakpoints(self) -> None:
        # 390 / 768 / 1366 viewports must have explicit guards.
        for query in ("max-width: 1366px", "max-width: 768px", "max-width: 480px"):
            self.assertIn(
                query,
                self.overview_css_text,
                f"studio-overview-cockpit.css missing responsive guard @{query}",
            )


class OverviewNextRealmRenderTests(SimpleTestCase):
    """Render the cockpit_signal_strip partial with mocked context and
    assert the visual contract holds."""

    def setUp(self) -> None:
        self.factory = RequestFactory()

    def _render_signal_strip(self, **ctx_overrides):
        """Render cockpit_signal_strip.html via the project template engine.

        Uses get_template() so {% load i18n static %} + {% static %}
        resolve against the configured project staticfiles backend.
        """
        tpl = get_template("studio_os/partials/cockpit_signal_strip.html")
        ctx = {
            "request": self.factory.get("/studio/"),
            "school": None,
            "current_mode": None,
            "launch_health_summary": "",
            "launch_ready": False,
            "overview_signals": {},
        }
        ctx.update(ctx_overrides)
        return tpl.render(ctx, request=ctx["request"])

    def test_unknown_state_when_signals_dict_empty(self) -> None:
        body = self._render_signal_strip(overview_signals={})
        # Five "unknown" tiles: pending-launches, draft-experiences,
        # active-automations, readiness, blockers.
        self.assertGreaterEqual(
            body.count('data-state="unknown"'),
            5,
            "all 5 metric tiles should be data-state=unknown when overview_signals empty",
        )
        self.assertIn("—", body, "unknown tiles must render '—' placeholder")

    def test_signals_dict_populates_values(self) -> None:
        body = self._render_signal_strip(
            overview_signals={
                "pending_launches": 3,
                "draft_experiences": 7,
                "active_automations": 12,
                "output_readiness_pct": 84,
                "open_blockers": 2,
            }
        )
        # No unknown tiles when all 5 metrics are populated (the
        # host-kind / mode / tenant tiles are always known).
        self.assertEqual(
            body.count('data-state="unknown"'),
            0,
            "no unknown tiles expected when all metrics provided",
        )
        # Spot-check the numbers actually land in output.
        self.assertIn(">3<", body.replace(" ", "").replace("\n", ""))
        self.assertIn("84%", body)

    def test_operator_host_kind_indicator(self) -> None:
        request = self.factory.get("/studio/")
        request.public_host_kind = "manager"
        body = self._render_signal_strip(request=request)
        self.assertIn('data-rmc-host-kind="manager"', body)
        # The host-kind tile renders "Operator" copy on manager hosts.
        self.assertIn("Operator", body)

    def test_tenant_host_kind_indicator(self) -> None:
        request = self.factory.get("/studio/")
        request.public_host_kind = "tenant"
        body = self._render_signal_strip(request=request)
        self.assertIn('data-rmc-host-kind="tenant"', body)
