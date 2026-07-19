"""Page fold standards template + asset contracts."""

from pathlib import Path

from django.test import SimpleTestCase


class PageFoldStandardsTests(SimpleTestCase):
    def test_portal_base_wires_fold_standards(self):
        text = Path("templates/portal_base.html").read_text(encoding="utf-8")
        chrome_styles = Path("templates/partials/rmc_platform_chrome_styles.html").read_text(
            encoding="utf-8"
        )
        chrome_scripts = Path("templates/partials/rmc_platform_chrome_scripts.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("back_to_top.html", text)
        self.assertIn("rmc_platform_chrome_styles.html", text)
        self.assertIn("rmc_platform_chrome_scripts.html", text)
        self.assertIn("rmc-page-fold-standards.css", chrome_styles)
        self.assertIn("rmc-page-fold-standards.js", chrome_scripts)
        self.assertIn("rmc-scroll-container.js", chrome_scripts)

    def test_control_plane_skeleton_wires_fold_standards(self):
        text = Path("templates/control_plane_skeleton.html").read_text(encoding="utf-8")
        chrome_scripts = Path("templates/partials/rmc_platform_chrome_scripts.html").read_text(
            encoding="utf-8"
        )
        self.assertTrue(
            "back_to_top.html" in text or "rmc_platform_chrome_scripts.html" in text
        )
        self.assertTrue(
            "rmc-page-fold-standards" in text
            or "rmc_platform_chrome_scripts.html" in text
            or "rmc-page-fold-standards.js" in chrome_scripts
        )

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
        self.assertIn("feature-cat-tabs", text)

    def test_chrome_wires_collapsable_platform_wide(self):
        styles = Path("templates/partials/rmc_platform_chrome_styles.html").read_text(
            encoding="utf-8"
        )
        scripts = Path("templates/partials/rmc_platform_chrome_scripts.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("rmc-collapsable.css", styles)
        self.assertIn("rmc-collapsable.js", scripts)

    def test_fold_js_compression_capabilities(self):
        js = Path("static/js/rmc-page-fold-standards.js").read_text(encoding="utf-8")
        css = Path("static/css/rmc-page-fold-standards.css").read_text(encoding="utf-8")
        for needle in (
            "initFoldStages",
            "initFieldsetAccordion",
            "initCardStackPagination",
            "initSecondaryFolds",
            "rmc-fold-stages",
        ):
            self.assertTrue(needle in js or needle in css, needle)

    def test_studio_experience_uses_fold_stages(self):
        text = Path("templates/studio_os/modes/experience.html").read_text(encoding="utf-8")
        self.assertIn("data-rmc-fold-stages", text)
        self.assertIn('data-rmc-fold-stage="builder"', text)
        self.assertIn('data-rmc-fold-stage="rollout"', text)
        self.assertIn('data-rmc-fold-stage="templates"', text)
        self.assertIn('data-rmc-page-fold-nav="required"', text)

    def test_cockpit_configure_fieldset_accordion(self):
        text = Path("templates/siteconfig/super/cockpit_configure.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('data-rmc-fieldset-accordion="1"', text)
        self.assertIn('data-rmc-page-fold-nav="required"', text)

    def test_theme_personality_fieldset_accordion(self):
        text = Path(
            "templates/siteconfig/super/theme_personality_configure.html"
        ).read_text(encoding="utf-8")
        self.assertIn('data-rmc-fieldset-accordion="1"', text)
        self.assertIn('data-rmc-page-fold-nav="required"', text)

    def test_marketing_voice_fieldset_accordion(self):
        text = Path(
            "templates/siteconfig/super/marketing_voice_configure.html"
        ).read_text(encoding="utf-8")
        self.assertIn('data-rmc-fieldset-accordion="1"', text)
        self.assertIn('data-rmc-page-fold-nav="required"', text)

    def test_tenant_app_catalog_fold_nav(self):
        text = Path("templates/marketplace/tenant_app_catalog.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('data-rmc-page-fold-nav="required"', text)
        self.assertIn('data-rmc-section-nav="auto"', text)

    def test_migration_and_support_fold_residuals(self):
        intake = Path("templates/migration_cloud/intake_new.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('data-rmc-page-fold-nav="required"', intake)
        ticket = Path(
            "templates/schools/super_support_ticket_detail.html"
        ).read_text(encoding="utf-8")
        self.assertIn('data-rmc-page-fold-nav="required"', ticket)
        start = Path(
            "templates/migration_cloud/customer/intake_start.html"
        ).read_text(encoding="utf-8")
        self.assertIn('data-rmc-fieldset-accordion="1"', start)
        self.assertIn('data-rmc-page-fold-nav="required"', start)
