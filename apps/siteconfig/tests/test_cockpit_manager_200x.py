"""Tests for cockpit manager 200x defaults + partials.

Covers:
- Each helper returns a dict with `enabled=False` by default.
- Each partial renders empty when `enabled=False` (no DOM markers).
- Each partial renders the expected DOM marker when `enabled=True` and
  payload data is present.
- BLEED PREVENTION: rendering each partial with
  `request.public_host_kind="portal"` produces empty output.

These tests intentionally avoid the orchestrator (`cockpit_context.py`)
so they remain stable while the orchestrator integrates 200x defaults
into the manager-host branch on its own schedule. We exercise the
partials directly with a synthetic `cockpit` dict.
"""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase

from apps.siteconfig.cockpit_manager_200x import (
    _manager_ai_copilot_defaults,
    _manager_audit_feed_defaults,
    _manager_forecast_defaults,
    _manager_heatmap_defaults,
    _manager_notebook_defaults,
    _manager_operator_presence_defaults,
    _manager_slo_clocks_defaults,
    _manager_trust_nutrition_defaults,
    _manager_waterfall_defaults,
    _manager_world_map_defaults,
    manager_200x_defaults,
)


# Mapping of partial filename ↔ context section key ↔ canonical DOM marker.
_PARTIAL_MATRIX: list[dict[str, str]] = [
    {
        "template": "partials/cockpit/_ai_copilot_rail.html",
        "section": "ai_copilot_rail",
        "marker": "rmc-app-shell__copilot",
    },
    {
        "template": "partials/cockpit/_live_world_map.html",
        "section": "live_world_map",
        "marker": "lx-world",
    },
    {
        "template": "partials/cockpit/_forecast_lane.html",
        "section": "forecast_lane",
        "marker": "lx-forecast",
    },
    {
        "template": "partials/cockpit/_operator_notebook.html",
        "section": "operator_notebook",
        "marker": "lx-notebook",
    },
    {
        "template": "partials/cockpit/_tenant_heatmap.html",
        "section": "tenant_heatmap",
        "marker": "lx-heatmap",
    },
    {
        "template": "partials/cockpit/_revenue_waterfall.html",
        "section": "revenue_waterfall",
        "marker": "lx-waterfall",
    },
    {
        "template": "partials/cockpit/_audit_feed.html",
        "section": "audit_feed",
        "marker": "lx-audit",
    },
    {
        "template": "partials/cockpit/_trust_nutrition.html",
        "section": "trust_nutrition",
        "marker": "lx-trust",
    },
    {
        "template": "partials/cockpit/_slo_clocks.html",
        "section": "slo_clocks",
        "marker": "lx-slo",
    },
    {
        "template": "partials/cockpit/_operator_presence.html",
        "section": "operator_presence",
        "marker": "cp-presence",
    },
]


def _enabled_payload(section: str) -> dict[str, Any]:
    """Return a section payload with `enabled=True` plus minimum data.

    Each section's gated partial needs SOME non-empty list/value or its
    inner conditional short-circuits even with enabled=True. We provide
    tiny but valid data for each.
    """
    base = manager_200x_defaults()[section]
    base["enabled"] = True

    if section == "ai_copilot_rail":
        base["insight_text"] = "Test insight"
    elif section == "live_world_map":
        base["schools_live"] = "127"
        base["tenant_dots"] = [{"cx": 100, "cy": 100, "color_token": "#a5b4fc", "ring_color": "#6366f1", "delay_s": 0.0}]
        base["regional_breakdown"] = [{"label": "Region", "count": "42", "dot_color_token": "indigo"}]
    elif section == "forecast_lane":
        base["cards"] = [{
            "slug": "mrr",
            "label": "MRR projection",
            "value": "$45.8k",
            "prediction": "predicted Wed +$3.8k",
            "stroke_color": "#22c55e",
            "fill_color": "rgba(34,197,94,0.10)",
            "past_points": [[0, 42], [120, 26]],
            "future_points": [[120, 26], [240, 12]],
            "band_path": "M120,28 Z",
            "today_x": 120,
            "caption_left": "past 7d",
            "caption_right": "ahead of plan",
        }]
    elif section == "operator_notebook":
        base["save_url"] = "/super/notebook/save/"
    elif section == "tenant_heatmap":
        base["tiles"] = [{"label": "Saint Sebastien Academy · healthy", "status": "healthy"}]
        base["meta_text"] = "168 tenants"
    elif section == "revenue_waterfall":
        base["bars"] = [{
            "slug": "start",
            "label": "Starting MRR",
            "value": "$39.2k",
            "x": 40, "y": 60, "width": 100, "height": 120,
            "gradient_id": "lx-wf-anchor",
            "value_color": "#1d1d1f",
        }]
        base["legend_rows"] = [{"label": "Starting", "value": "$39.2k", "tone": "neutral"}]
    elif section == "audit_feed":
        base["events"] = [{
            "time": "14:38:02",
            "actor": "admin",
            "event": "companion.upload accepted",
            "scope": "tenant#a4f1",
            "severity": "ok",
            "severity_label": "OK",
        }]
    elif section == "trust_nutrition":
        base["rows"] = [{"label": "Uptime · 30d", "value": "99.987%", "status": "ok"}]
    elif section == "slo_clocks":
        base["clocks"] = [{
            "label": "P99 latency budget",
            "value": "32",
            "value_suffix": "m left",
            "sublabel": "api · 28d window",
            "dot_status": "ok",
        }]
    elif section == "operator_presence":
        base["avatars"] = [{"initials": "AD", "gradient_slug": "indigo"}]
        base["operators_online_count"] = 3
        base["status_pill_text"] = "All systems handling well"
    return base


class CockpitManager200xDefaultsTests(SimpleTestCase):
    """Helpers return well-formed defaults with `enabled=False`."""

    def test_aggregator_returns_all_ten_sections(self):
        payload = manager_200x_defaults()
        expected = {
            "ai_copilot_rail",
            "live_world_map",
            "forecast_lane",
            "operator_notebook",
            "tenant_heatmap",
            "revenue_waterfall",
            "audit_feed",
            "trust_nutrition",
            "slo_clocks",
            "operator_presence",
        }
        self.assertEqual(set(payload.keys()), expected)

    def test_every_section_defaults_to_disabled(self):
        for section, payload in manager_200x_defaults().items():
            with self.subTest(section=section):
                self.assertIn("enabled", payload, f"{section} missing 'enabled' key")
                self.assertFalse(payload["enabled"], f"{section} enabled should default False")

    def test_individual_helpers_return_dicts(self):
        helpers = [
            _manager_ai_copilot_defaults,
            _manager_world_map_defaults,
            _manager_forecast_defaults,
            _manager_notebook_defaults,
            _manager_heatmap_defaults,
            _manager_waterfall_defaults,
            _manager_audit_feed_defaults,
            _manager_trust_nutrition_defaults,
            _manager_slo_clocks_defaults,
            _manager_operator_presence_defaults,
        ]
        for helper in helpers:
            with self.subTest(helper=helper.__name__):
                payload = helper()
                self.assertIsInstance(payload, dict)
                self.assertIn("enabled", payload)
                self.assertFalse(payload["enabled"])


class CockpitManager200xPartialRenderTests(SimpleTestCase):
    """Each partial renders empty when disabled and DOM marker when enabled."""

    def setUp(self) -> None:
        self.factory = RequestFactory()

    def _manager_request(self):
        request = self.factory.get("/super/")
        request.public_host_kind = "manager"
        request.user = type("U", (), {"is_authenticated": True, "is_staff": True})()
        return request

    def _portal_request(self):
        request = self.factory.get("/portal/")
        request.public_host_kind = "portal"
        request.user = type("U", (), {"is_authenticated": True, "is_staff": False})()
        return request

    def test_each_partial_renders_empty_when_disabled(self):
        for entry in _PARTIAL_MATRIX:
            with self.subTest(template=entry["template"]):
                context = {
                    "cockpit": manager_200x_defaults(),
                    "csrf_token": "test-token",
                }
                rendered = render_to_string(entry["template"], context=context, request=self._manager_request())
                stripped = rendered.strip()
                self.assertEqual(
                    stripped, "",
                    f"{entry['template']} should render empty when disabled, got: {stripped[:80]!r}",
                )

    def test_each_partial_renders_marker_when_enabled(self):
        for entry in _PARTIAL_MATRIX:
            with self.subTest(template=entry["template"]):
                cockpit = manager_200x_defaults()
                cockpit[entry["section"]] = _enabled_payload(entry["section"])
                context = {"cockpit": cockpit, "csrf_token": "test-token"}
                rendered = render_to_string(entry["template"], context=context, request=self._manager_request())
                self.assertIn(
                    entry["marker"], rendered,
                    f"{entry['template']} did not emit marker {entry['marker']!r} when enabled",
                )


class CockpitManager200xBleedPreventionTests(SimpleTestCase):
    """Rendering a manager partial on a portal request must not leak DOM.

    The partials self-gate on `cockpit.<section>.enabled`. For a portal
    request, the orchestrator returns NO 200x sections (only the tenant
    footer / community band / newsletter band keys), so accessing
    `cockpit.ai_copilot_rail.enabled` resolves to empty and the
    `{% if %}` short-circuits.
    """

    def setUp(self) -> None:
        self.factory = RequestFactory()

    def _portal_request(self):
        request = self.factory.get("/portal/")
        request.public_host_kind = "portal"
        request.user = type("U", (), {"is_authenticated": True, "is_staff": False})()
        return request

    def test_partials_render_empty_with_portal_host_and_no_cockpit_keys(self):
        # Portal-host cockpit dict has NO manager-200x keys at all.
        cockpit_portal_only: dict[str, Any] = {
            "footer": {},
            "community_band": {"enabled": False},
            "newsletter_band": {"enabled": False},
        }
        for entry in _PARTIAL_MATRIX:
            with self.subTest(template=entry["template"]):
                context = {"cockpit": cockpit_portal_only, "csrf_token": "test-token"}
                rendered = render_to_string(entry["template"], context=context, request=self._portal_request())
                stripped = rendered.strip()
                self.assertEqual(
                    stripped, "",
                    f"{entry['template']} bled into portal host, got: {stripped[:80]!r}",
                )
                self.assertNotIn(entry["marker"], rendered)
