"""Page fold standards template + asset contracts."""

from pathlib import Path

from django.test import SimpleTestCase


class PageFoldStandardsTests(SimpleTestCase):
    def test_portal_base_wires_fold_standards(self):
        text = Path("templates/portal_base.html").read_text(encoding="utf-8")
        self.assertIn("back_to_top.html", text)
        self.assertIn("rmc-page-fold-standards.css", text)
        self.assertIn("rmc-page-fold-standards.js", text)
        self.assertIn("rmc-scroll-container.js", text)

    def test_control_plane_skeleton_wires_fold_standards(self):
        text = Path("templates/control_plane_skeleton.html").read_text(encoding="utf-8")
        self.assertIn("back_to_top.html", text)
        self.assertIn("rmc-page-fold-standards", text)

    def test_portal_and_cp_shell_fold_nav(self):
        portal = Path("templates/portal_base.html").read_text(encoding="utf-8")
        cp = Path("templates/control_plane_base.html").read_text(encoding="utf-8")
        self.assertIn('data-rmc-page-fold-nav="required"', portal)
        self.assertIn("public_host_kind == 'manager'", portal)
        self.assertIn('data-rmc-page-fold-nav="required"', cp)

    def test_feature_control_audit_paginated_view(self):
        src = Path("apps/siteconfig/views_feature_control.py").read_text(encoding="utf-8")
        self.assertIn("def feature_control_audit_log", src)
        self.assertIn("Paginator(qs, 25)", src)
        audit = Path(
            "templates/siteconfig/partials/feature_control_audit_body.html"
        ).read_text(encoding="utf-8")
        self.assertIn("components/pagination.html", audit)

    def test_feature_control_task_pagination_markers(self):
        text = Path(
            "templates/siteconfig/feature_control_panel_content.html"
        ).read_text(encoding="utf-8")
        self.assertIn('data-rmc-page-fold-nav="required"', text)
        self.assertIn('data-rmc-scroll-policy="paginate"', text)
        self.assertIn("rmc-page-fold-nav--sticky", text)
