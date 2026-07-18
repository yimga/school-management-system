"""Tests for the admin change-form live preview contract (§3.5)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MODE_PANELS = REPO / "templates" / "admin" / "includes" / "admin_change_form_mode_panels.html"
CHANGE_FORM = REPO / "templates" / "admin" / "change_form.html"
WORKSPACE_JS = REPO / "static" / "js" / "rmc-admin-workspace.js"


class TestModePanelsCTAs(unittest.TestCase):
    """Mode panels template has popout and new-tab CTAs."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.content = MODE_PANELS.read_text(encoding="utf-8")

    def test_has_popout_cta(self):
        self.assertIn('data-rmc-django-preview-open="popout"', self.content)

    def test_has_tab_cta(self):
        self.assertIn('data-rmc-django-preview-open="tab"', self.content)

    def test_has_drawer_cta(self):
        self.assertIn('data-rmc-django-preview-open="drawer"', self.content)

    def test_has_preview_url_data_attribute(self):
        self.assertIn("data-rmc-admin-preview-url", self.content)

    def test_has_iframe_mount_point(self):
        self.assertIn("data-rmc-django-preview-iframe-mount", self.content)

    def test_honest_copy_when_no_url(self):
        self.assertIn("No preview URL available", self.content)


class TestChangeFormPreviewUrl(unittest.TestCase):
    """change_form.html workspace carries data-rmc-admin-preview-url."""

    def test_workspace_has_preview_url_attribute(self):
        content = CHANGE_FORM.read_text(encoding="utf-8")
        self.assertIn("data-rmc-admin-preview-url", content)


class TestWorkspaceJSPreviewModes(unittest.TestCase):
    """rmc-admin-workspace.js handles popout, tab, and iframe mount."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.js = WORKSPACE_JS.read_text(encoding="utf-8")

    def test_resolves_preview_url(self):
        self.assertIn("resolvePreviewUrl", self.js)

    def test_handles_popout(self):
        self.assertIn("openPreviewPopout", self.js)

    def test_handles_tab(self):
        self.assertIn("openPreviewTab", self.js)

    def test_popup_blocked_fallback(self):
        self.assertIn("openPreviewDrawer", self.js)
        self.assertRegex(self.js, r"if\s*\(\s*!w\s*\|\|\s*w\.closed\s*\)")

    def test_mounts_iframe_in_drawer(self):
        self.assertIn("mountIframeInDrawer", self.js)

    def test_mounts_iframe_in_stage(self):
        self.assertIn("mountIframeInStage", self.js)

    def test_dispatch_on_mode(self):
        popout_re = re.compile(r'mode\s*===\s*"popout"')
        tab_re = re.compile(r'mode\s*===\s*"tab"')
        self.assertRegex(self.js, popout_re)
        self.assertRegex(self.js, tab_re)


if __name__ == "__main__":
    unittest.main()
