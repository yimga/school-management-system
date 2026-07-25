"""Tests for the honest admin change-form Form/Audit contract."""

from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MODE_PANELS = REPO / "templates" / "admin" / "includes" / "admin_change_form_mode_panels.html"
CHANGE_FORM = REPO / "templates" / "admin" / "change_form.html"
WORKSPACE_JS = REPO / "static" / "js" / "rmc-admin-workspace.js"


class TestModePanelsContract(unittest.TestCase):
    """Generic admin chrome must not advertise an unimplemented preview."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.content = MODE_PANELS.read_text(encoding="utf-8")

    def test_has_audit_panel(self):
        self.assertIn('data-rmc-django-mode-panel="audit"', self.content)

    def test_has_no_generic_preview_cta_or_iframe(self):
        for legacy in (
            "data-rmc-django-preview-open",
            "data-rmc-admin-preview-url",
            "data-rmc-django-preview-iframe-mount",
            "<iframe",
        ):
            self.assertNotIn(legacy, self.content)


class TestChangeFormModes(unittest.TestCase):
    """The shared form exposes only modes backed by a real surface."""

    def test_workspace_has_form_and_audit_only(self):
        content = CHANGE_FORM.read_text(encoding="utf-8")
        # v15 Admin OS collapsed the Form/Audit *view toggle* into a single form
        # canvas: change_form ships the "form" view-mode and reaches audit via the
        # History affordance + in-workbench Save. The toggle chrome
        # (data-rmc-django-view="…") and the mode-panels include are now forbidden
        # (see scripts/audit_django_admin_canvas_contract.py). Preview stays absent.
        self.assertIn('data-rmc-django-view-mode="form"', content)
        self.assertIn('data-rmc-django-mode-panel="form"', content)
        # Audit surface = History affordance in the command band (not a fake toggle).
        self.assertIn("rmc-django-band-action", content)
        # No Form/Audit toggle chrome, no mode-panels include, and no fake preview.
        self.assertNotIn("data-rmc-django-view-toggle", content)
        self.assertNotIn("admin_change_form_mode_panels.html", content)
        self.assertNotIn('data-rmc-django-view="preview"', content)
        self.assertNotIn("data-rmc-admin-preview-url", content)


class TestWorkspaceJSHonestModes(unittest.TestCase):
    """The runtime migrates stale Preview state without creating fake UI."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.js = WORKSPACE_JS.read_text(encoding="utf-8")

    def test_migrates_stale_preview_mode_to_form(self):
        self.assertIn('if (mode === "preview") mode = "form";', self.js)
        self.assertIn('if (stored === "preview") stored = "form";', self.js)

    def test_allows_only_form_and_audit(self):
        self.assertIn("var allowed = { form: 1, audit: 1 };", self.js)

    def test_does_not_build_generic_preview_surfaces(self):
        for legacy in (
            "ensurePreviewDrawer",
            "openPreviewDrawer",
            "openPreviewPopout",
            "openPreviewTab",
            "mountIframeInDrawer",
            "mountIframeInStage",
        ):
            self.assertNotIn(legacy, self.js)


if __name__ == "__main__":
    unittest.main()
