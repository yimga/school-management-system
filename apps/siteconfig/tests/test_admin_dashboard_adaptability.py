from __future__ import annotations

from copy import deepcopy
import re
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.dashboard.admin_context import build_admin_dashboard_context
from apps.siteconfig.contrast_guard import meets_contrast
from apps.platform_runtime.helpers import get_platform_site_settings_record

User = get_user_model()


def _platform_admin_uses_unfold_shell() -> bool:
    """Unfold replaces the legacy admin/index + admin_dashboard stack on platform /admin/."""
    return bool(getattr(settings, "UNFOLD", None))


class AdminDashboardWidgetRegistryTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.superuser = User.objects.create_superuser(
            username="admin-widget-tests",
            email="admin-widget-tests@example.com",
            password="password",
        )

    def _request(self):
        request = self.factory.get("/admin/")
        request.user = self.superuser
        request.session = {}
        return request

    def test_widget_registry_exposes_contract_metadata(self):
        context = build_admin_dashboard_context(self._request(), base_context={})
        registry = context.get("dashboard_widget_registry")
        self.assertIsInstance(registry, list)
        self.assertGreaterEqual(len(registry), 5)

        ids = {entry.get("id") for entry in registry}
        expected_ids = {
            "kpi_cards",
            "security_compliance",
            "action_queue",
            "settings_audit",
            "admin_controls",
        }
        self.assertTrue(expected_ids.issubset(ids))

        for entry in registry:
            self.assertIn("id", entry)
            self.assertIn("template", entry)
            self.assertIn("cache_ttl_seconds", entry)
            self.assertIn("cache_scope", entry)
            self.assertIn("enabled", entry)

    def test_widget_cache_hits_on_second_context_build(self):
        cache.clear()
        first_context = build_admin_dashboard_context(self._request(), base_context={})
        second_context = build_admin_dashboard_context(self._request(), base_context={})

        first_hits = first_context.get("dashboard_widget_cache_hits", {})
        second_hits = second_context.get("dashboard_widget_cache_hits", {})

        self.assertIn("kpi_cards", first_hits)
        self.assertIn("kpi_cards", second_hits)
        self.assertFalse(first_hits["kpi_cards"])
        self.assertTrue(second_hits["kpi_cards"])

        first_timings = first_context.get("dashboard_widget_timings_ms", {})
        second_timings = second_context.get("dashboard_widget_timings_ms", {})
        self.assertIn("kpi_cards", first_timings)
        self.assertIn("kpi_cards", second_timings)
        self.assertGreaterEqual(first_timings["kpi_cards"], 0.0)
        self.assertGreaterEqual(second_timings["kpi_cards"], 0.0)

    def test_context_exposes_weather_and_telemetry_contract(self):
        context = build_admin_dashboard_context(self._request(), base_context={})

        weather = context.get("admin_weather")
        self.assertIsInstance(weather, dict)
        for key in (
            "enabled",
            "label",
            "latitude",
            "longitude",
            "temperature_unit",
            "timezone",
        ):
            self.assertIn(key, weather)

        telemetry = context.get("dashboard_widget_telemetry")
        self.assertIsInstance(telemetry, list)
        self.assertTrue(telemetry)
        for row in telemetry:
            self.assertIn("id", row)
            self.assertIn("timing_ms", row)
            self.assertIn("cache_hit", row)


class AdminDashboardResponsiveSnapshotTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="admin-responsive-tests",
            email="admin-responsive-tests@example.com",
            password="password",
        )

    @unittest.skipIf(
        _platform_admin_uses_unfold_shell(),
        "Unfold admin index does not render legacy admin_dashboard HTML markers.",
    )
    def test_admin_dashboard_layout_contract_has_responsive_markers(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8", errors="ignore")

        required_markers = [
            'class="admin-kpi-grid dashboard-card-grid dashboard-card-grid--dense"',
            'data-dashboard-column="main"',
            'data-dashboard-column="lower"',
            'data-widget-id="admin-calendar-widget"',
            'data-widget-id="admin-controls"',
            'class="admin-security-row"',
        ]
        for marker in required_markers:
            self.assertIn(marker, html)

    @unittest.skipIf(
        _platform_admin_uses_unfold_shell(),
        "Unfold uses its own index template chain; admin/index.html is not the entrypoint.",
    )
    def test_admin_index_template_is_canonical_entrypoint(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)

        template_names = {
            template.name for template in response.templates if template.name
        }
        self.assertIn("admin/index.html", template_names)
        self.assertIn("admin/admin_dashboard.html", template_names)

        index_template = Path(settings.BASE_DIR) / "templates" / "admin" / "index.html"
        content = index_template.read_text(encoding="utf-8", errors="ignore")
        self.assertIn('{% extends "admin/admin_dashboard.html" %}', content)

    def test_dashboard_auto_grid_css_breakpoint_contract(self):
        css_path = (
            Path(settings.BASE_DIR) / "static" / "css" / "dashboard-auto-grid.css"
        )
        content = css_path.read_text(encoding="utf-8", errors="ignore")

        self.assertIn(".dashboard-card-grid", content)
        self.assertIn(".dashboard-card-grid--dense", content)
        self.assertIn("@media (max-width: 767.98px)", content)
        self.assertIn("@media (max-width: 575.98px)", content)

    @unittest.skipIf(
        _platform_admin_uses_unfold_shell(),
        "admin_dashboard.html may embed scoped <style> blocks; Unfold is the live shell.",
    )
    def test_dashboard_template_sources_avoid_inline_style_attributes(self):
        template_root = Path(settings.BASE_DIR) / "templates" / "admin"
        paths = [
            template_root / "admin_dashboard.html",
            template_root / "components" / "dashboard_kpi_card.html",
            template_root / "components" / "dashboard_control_link.html",
            template_root / "components" / "dashboard_security_stat.html",
            template_root / "components" / "dashboard_system_info_row.html",
            template_root / "components" / "dashboard_settings_change_row.html",
        ]
        for path in paths:
            content = path.read_text(encoding="utf-8", errors="ignore")
            self.assertNotIn('style="', content, msg=f"Inline style found in {path}")

    @unittest.skipIf(
        _platform_admin_uses_unfold_shell(),
        "Platform admin index uses index_superadmin.html; admin_dashboard.html is a redirect shim.",
    )
    def test_admin_dashboard_template_uses_static_security_assets(self):
        dashboard_template = (
            Path(settings.BASE_DIR) / "templates" / "admin" / "admin_dashboard.html"
        )
        content = dashboard_template.read_text(encoding="utf-8", errors="ignore")
        self.assertIn("index_superadmin.html", content)

    def test_admin_weather_templates_use_internal_weather_api(self):
        # admin/admin_dashboard.html is a deprecated 12-line redirect stub (it just
        # {% extends "admin/index_superadmin.html" %}); the weather marquee that used
        # to live there is now the standalone weather_marquee.html component, which is
        # the template that must reference the internal api_admin_weather proxy.
        admin_paths = [
            Path(settings.BASE_DIR)
            / "templates"
            / "components"
            / "weather_marquee.html",
        ]
        context_paths = [
            Path(settings.BASE_DIR)
            / "templates"
            / "components"
            / "header_weather_widget.html",
            Path(settings.BASE_DIR)
            / "templates"
            / "components"
            / "backend_datetime_weather.html",
            Path(settings.BASE_DIR)
            / "templates"
            / "components"
            / "weather_widget.html",
        ]

        for path in admin_paths:
            content = path.read_text(encoding="utf-8", errors="ignore")
            self.assertNotIn(
                "api.open-meteo.com",
                content,
                msg=f"Direct weather provider call found in {path}",
            )
            self.assertIn(
                "api_admin_weather",
                content,
                msg=f"Internal weather API not referenced in {path}",
            )

        for path in context_paths:
            content = path.read_text(encoding="utf-8", errors="ignore")
            self.assertNotIn(
                "api.open-meteo.com",
                content,
                msg=f"Direct weather provider call found in {path}",
            )
            self.assertIn(
                "api_weather_context",
                content,
                msg=f"Context weather API not referenced in {path}",
            )


class AdminDashboardWeatherApiTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="admin-weather-tests",
            email="admin-weather-tests@example.com",
            password="password",
        )
        self.site = get_platform_site_settings_record(create=True)
        self._initial_flags = deepcopy(self.site.backend_feature_flags or {})
        cache.clear()

    def tearDown(self):
        from apps.siteconfig.tests.payload_helpers import persist_runtime_site_settings_payload

        persist_runtime_site_settings_payload(
            backend_feature_flags=deepcopy(self._initial_flags)
        )
        cache.clear()

    def _set_weather_flags(self, **updates):
        from apps.siteconfig.tests.payload_helpers import persist_runtime_site_settings_payload

        flags = deepcopy(self.site.backend_feature_flags or {})
        flags.update(updates)
        persist_runtime_site_settings_payload(backend_feature_flags=flags)
        self.site.refresh_from_db()

    def test_weather_api_requires_observability_auth(self):
        response = self.client.get(reverse("api_admin_weather"))
        self.assertEqual(response.status_code, 403)

    def test_weather_api_returns_disabled_payload_without_provider_call(self):
        self.client.force_login(self.superuser)
        self._set_weather_flags(show_header_context_weather=False)

        with patch("apps.observability.views.requests.get") as mocked_get:
            response = self.client.get(reverse("api_admin_weather"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("status"), "disabled")
        self.assertFalse(payload.get("enabled"))
        self.assertIsNone(payload.get("weather"))
        mocked_get.assert_not_called()

    def test_weather_api_uses_cache_after_first_fetch(self):
        self.client.force_login(self.superuser)
        self._set_weather_flags(
            show_header_context_weather=True,
            header_weather_latitude=4.1527,
            header_weather_longitude=9.241,
            header_weather_temperature_unit="celsius",
            header_weather_timezone="Africa/Douala",
            header_weather_label="Buea, Cameroon",
        )

        provider_response = Mock()
        provider_response.raise_for_status.return_value = None
        provider_response.json.return_value = {
            "current": {
                "temperature_2m": 24.7,
                "weather_code": 2,
            }
        }

        with patch(
            "apps.observability.views.requests.get", return_value=provider_response
        ) as mocked_get:
            first = self.client.get(reverse("api_admin_weather"))
            second = self.client.get(reverse("api_admin_weather"))

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        first_payload = first.json()
        second_payload = second.json()

        self.assertEqual(first_payload.get("status"), "success")
        self.assertFalse(first_payload.get("cached"))
        self.assertEqual(first_payload.get("temperature_unit"), "celsius")
        self.assertEqual(first_payload.get("label"), "Buea, Cameroon")
        self.assertEqual(first_payload.get("weather", {}).get("weather_code"), 2)
        self.assertAlmostEqual(
            first_payload.get("weather", {}).get("temperature"), 24.7
        )

        self.assertEqual(second_payload.get("status"), "success")
        self.assertTrue(second_payload.get("cached"))
        self.assertEqual(mocked_get.call_count, 1)

    def test_weather_context_api_allows_anonymous_and_caches(self):
        self._set_weather_flags(
            show_header_context_weather=True,
            header_weather_latitude=4.1527,
            header_weather_longitude=9.241,
            header_weather_temperature_unit="celsius",
            header_weather_timezone="Africa/Douala",
            header_weather_label="Buea, Cameroon",
        )

        provider_response = Mock()
        provider_response.raise_for_status.return_value = None
        provider_response.json.return_value = {
            "current": {
                "temperature_2m": 26.2,
                "weather_code": 1,
            }
        }

        with patch(
            "apps.observability.views.requests.get", return_value=provider_response
        ) as mocked_get:
            first = self.client.get(reverse("api_weather_context"))
            second = self.client.get(reverse("api_weather_context"))

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        first_payload = first.json()
        second_payload = second.json()

        self.assertEqual(first_payload.get("status"), "success")
        self.assertFalse(first_payload.get("cached"))
        self.assertEqual(first_payload.get("weather", {}).get("weather_code"), 1)
        self.assertAlmostEqual(
            first_payload.get("weather", {}).get("temperature"), 26.2
        )
        self.assertEqual(second_payload.get("status"), "success")
        self.assertTrue(second_payload.get("cached"))
        self.assertEqual(mocked_get.call_count, 1)

    def test_weather_context_api_disabled_payload_without_provider_call(self):
        self._set_weather_flags(show_header_context_weather=False)

        with patch("apps.observability.views.requests.get") as mocked_get:
            response = self.client.get(reverse("api_weather_context"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("status"), "disabled")
        self.assertFalse(payload.get("enabled"))
        self.assertIsNone(payload.get("weather"))
        mocked_get.assert_not_called()

    def test_weather_context_api_skips_provider_when_coords_unset(self):
        self._set_weather_flags(
            show_header_context_weather=True,
            header_weather_latitude=0.0,
            header_weather_longitude=0.0,
        )

        with patch("apps.observability.views.requests.get") as mocked_get:
            response = self.client.get(reverse("api_weather_context"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("status"), "degraded")
        self.assertTrue(payload.get("enabled"))
        self.assertIsNone(payload.get("weather"))
        mocked_get.assert_not_called()

    def test_weather_context_api_backs_off_after_rate_limit(self):
        self._set_weather_flags(
            show_header_context_weather=True,
            header_weather_latitude=4.1527,
            header_weather_longitude=9.241,
            header_weather_temperature_unit="celsius",
            header_weather_timezone="Africa/Douala",
            header_weather_label="Buea, Cameroon",
        )

        rate_limited = Mock()
        rate_limited.status_code = 429
        http_error = requests.HTTPError("429 Too Many Requests", response=rate_limited)
        rate_limited.raise_for_status.side_effect = http_error

        with patch(
            "apps.observability.views.requests.get", return_value=rate_limited
        ) as mocked_get:
            first = self.client.get(reverse("api_weather_context"))
            second = self.client.get(reverse("api_weather_context"))

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json().get("status"), "degraded")
        self.assertEqual(second.json().get("status"), "degraded")
        self.assertEqual(mocked_get.call_count, 1)


class AdminDashboardAccessibilityContractTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="admin-a11y-tests",
            email="admin-a11y-tests@example.com",
            password="password",
        )

    @unittest.skipIf(
        _platform_admin_uses_unfold_shell(),
        "Unfold admin shell uses different heading/ARIA structure than legacy dashboard.",
    )
    def test_admin_dashboard_heading_and_aria_contract(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8", errors="ignore")

        heading_levels = [int(level) for level in re.findall(r"<h([1-6])\b", html)]
        self.assertTrue(
            heading_levels, "Expected at least one heading on admin dashboard."
        )
        self.assertIn(1, heading_levels)
        self.assertIn(2, heading_levels)
        self.assertIn('class="admin-dash__title"', html)
        self.assertIn('class="admin-controls__title"', html)

        self.assertIn('aria-label="Previous month"', html)
        self.assertIn('aria-label="Next month"', html)
        self.assertIn("admin-logo-img", html)
        self.assertIn('admin-kpi-card__icon" aria-hidden="true"', html)
        self.assertIn('weather-widget__icon" id="weatherIcon" aria-hidden="true"', html)

    def test_default_admin_palette_contrast_contract(self):
        self.assertTrue(meets_contrast("#0f172a", "#f8fafc", 4.5))
        self.assertTrue(meets_contrast("#475569", "#ffffff", 4.5))

    @unittest.skipIf(
        _platform_admin_uses_unfold_shell(),
        "Legacy dashboard widget telemetry panel is not rendered in Unfold shell.",
    )
    @override_settings(DEBUG=True)
    def test_debug_widget_telemetry_panel_renders(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8", errors="ignore")
        self.assertIn('data-widget-id="admin-widget-telemetry"', html)
        self.assertIn("Dashboard Widget Telemetry", html)
