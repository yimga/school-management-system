"""Magic UX contract: measurement JS kinds + on-disk template markers (no DB / no render)."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class PlatformBehaviorMeasurementContractTests(SimpleTestCase):
    """Ensures platform_behavior_track.js retains the measurement vocabulary."""

    def test_js_exports_click_screen_transition_task_boundaries(self):
        path = Path(settings.BASE_DIR) / "static" / "js" / "platform_behavior_track.js"
        text = path.read_text(encoding="utf-8", errors="replace")
        self.assertIn('kind: "click"', text)
        self.assertIn('kind: "screen_transition"', text)
        self.assertIn('kind: kind', text)  # task_start / task_complete payloads
        self.assertIn('kind !== "task_start"', text)
        self.assertIn('kind !== "task_complete"', text)
        self.assertIn("rmcClickTaskBoundary", text)
        self.assertIn("window.rmcClickTaskBoundary", text)


class MagicUxTemplateLiteralMarkersTests(SimpleTestCase):
    """Source-level assertions for strict UX blocks (survives template refactors if strings kept)."""

    def test_studio_os_shell_strict_toolbar(self):
        path = Path(settings.BASE_DIR) / "templates" / "studio_os" / "shell.html"
        text = path.read_text(encoding="utf-8", errors="replace")
        self.assertIn("rmc_conversion_single_action_enforced", text)
        self.assertIn('data-task="studio_os"', text)
        self.assertIn("rmc-conversion-more-actions", text)
        self.assertIn("Open Experience", text)

    def test_installation_health_strict_hero(self):
        path = Path(settings.BASE_DIR) / "templates" / "marketplace" / "installation_health.html"
        text = path.read_text(encoding="utf-8", errors="replace")
        # installation_health adopted the shared operational-center frame; the
        # bespoke hero markers were replaced by the frame's masthead primary CTA
        # (primary_url/primary_label) + jump nav.
        self.assertIn("rmc_operational_center_frame.html", text)
        self.assertIn('primary_label=_("View health")', text)

    def test_tenant_installed_apps_links_catalog(self):
        path = Path(settings.BASE_DIR) / "templates" / "marketplace" / "tenant_installed_apps.html"
        text = path.read_text(encoding="utf-8", errors="replace")
        self.assertIn("tenant_app_catalog", text)
