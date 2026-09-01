"""Magic UX contract: measurement JS kinds + on-disk template markers (no DB / no render)."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_markup, assert_wires


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
        # rmc_conversion_single_action_enforced is an {% if %} condition and
        # "Open Experience" is a {% trans %} msgid: both are template CODE, which
        # no parse and no render of the file can see, so both stay reads.
        self.assertIn("rmc_conversion_single_action_enforced", text)
        self.assertIn("Open Experience", text)
        # The two toolbar hooks ARE markup, so ask what the shell EMITS.
        assert_markup(self, path, 'data-task="studio_os"', "rmc-conversion-more-actions")

    def test_installation_health_strict_hero(self):
        path = Path(settings.BASE_DIR) / "templates" / "marketplace" / "installation_health.html"
        text = path.read_text(encoding="utf-8", errors="replace")
        # installation_health adopted the shared operational-center frame; the
        # bespoke hero markers were replaced by the frame's masthead primary CTA
        # (primary_url/primary_label) + jump nav.
        # primary_label is an {% include ... with %} argument -- template code, so
        # that assertion stays a read.
        self.assertIn('primary_label=_("View health")', text)
        # "Adopted the frame" is a wiring claim and a parse can settle it: a
        # {% comment %} leaves the filename in the bytes and builds no IncludeNode.
        assert_wires(self, path, "rmc_operational_center_frame.html")

    def test_tenant_installed_apps_links_catalog(self):
        path = Path(settings.BASE_DIR) / "templates" / "marketplace" / "tenant_installed_apps.html"
        text = path.read_text(encoding="utf-8", errors="replace")
        # The route name only ever exists as a {% url %} argument, so the source
        # read is the only thing that can see it.
        self.assertIn("tenant_app_catalog", text)
        # The anchor that carries that {% url %} is tagged with these two markers,
        # and they are emitted text -- so this asserts the catalog link is on the
        # page rather than merely spelled somewhere in the file.
        assert_markup(
            self,
            path,
            'data-action="marketplace-browse-catalog"',
            'data-task-step="marketplace:installed-footer-catalog"',
        )
