"""Page fold standards template + asset contracts.

Rewritten 2026-09-01. Every template assertion in this file used to read the
template as TEXT -- ``assertIn("back_to_top.html", Path(t).read_text())`` -- and
11 of the 13 tests were measured VACUOUS by
scripts/verify_test_asserts_behaviour.py: they still passed when the template
was replaced by a ``{% comment %}`` block containing the very strings they
assert. They checked that a WORD appeared in a file, not that the shell wired
anything.

Each is now asked of the template ENGINE instead, at the strongest level the
template in question supports:

    assert_wires     the partial is really {% include %}d   -- a comment is not a node
    assert_markup    the attribute is really emitted        -- a comment yields no TextNode
    assert_renders   the asset URL is really produced       -- a comment renders ""

All three fail under the harness's mutation, which is what SOUND means. None of
them needs a database or a request: these are parses and standalone renders, so
SimpleTestCase still holds and the file stays fast.
"""

from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import (
    assert_markup,
    assert_renders,
    assert_wires,
    wired_in,
)

PORTAL_BASE = "templates/portal_base.html"
CP_BASE = "templates/control_plane_base.html"
CP_SKELETON = "templates/control_plane_skeleton.html"
CHROME_STYLES = "templates/partials/rmc_platform_chrome_styles.html"
CHROME_SCRIPTS = "templates/partials/rmc_platform_chrome_scripts.html"

FOLD_NAV = 'data-rmc-page-fold-nav="required"'
FIELDSET_ACCORDION = 'data-rmc-fieldset-accordion="1"'


class PageFoldStandardsTests(SimpleTestCase):
    def test_portal_base_wires_fold_standards(self):
        assert_wires(
            self,
            PORTAL_BASE,
            "back_to_top.html",
            "rmc_platform_chrome_styles.html",
            "rmc_platform_chrome_scripts.html",
        )
        assert_renders(self, CHROME_STYLES, "rmc-page-fold-standards.css")
        assert_renders(
            self,
            CHROME_SCRIPTS,
            "rmc-page-fold-standards.js",
            "rmc-scroll-container.js",
        )

    def test_control_plane_skeleton_wires_fold_standards(self):
        wired = wired_in(CP_SKELETON)
        reaches_chrome = any(
            name.endswith("/rmc_platform_chrome_scripts.html") for name in wired
        )
        self.assertTrue(
            reaches_chrome
            or any(name.endswith("/back_to_top.html") for name in wired),
            f"{CP_SKELETON} wires neither the chrome scripts partial nor "
            f"back_to_top; it wires {sorted(wired)}",
        )
        # The original allowed the fold-standards script to arrive either way.
        # Keep that disjunction, but make each arm prove delivery rather than
        # spelling: through the chrome partial, the partial must render the
        # script; direct, the skeleton must emit the marker itself.
        if reaches_chrome:
            assert_renders(self, CHROME_SCRIPTS, "rmc-page-fold-standards.js")
        else:
            assert_markup(self, CP_SKELETON, "rmc-page-fold-standards")

    def test_portal_and_cp_shell_fold_nav(self):
        assert_markup(self, PORTAL_BASE, FOLD_NAV)
        assert_markup(self, CP_BASE, FOLD_NAV)
        # Template LOGIC, not output. A condition is not something a page
        # emits, so reading the source is the only way to see it. It is safe to
        # keep here precisely because the two assertions above already fail
        # when the shell stops emitting anything -- they are what make this
        # test sound, and this line only adds detail on top.
        self.assertIn(
            "public_host_kind == 'manager'",
            Path(PORTAL_BASE).read_text(encoding="utf-8"),
        )

    def test_feature_control_audit_paginated_view(self):
        # A .py source read is a different question from a template one and is
        # not what the vacuity harness measures -- there is no rendering step
        # to skip. Left as it was.
        src = Path("apps/siteconfig/views_feature_control.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("def feature_control_audit_log", src)
        self.assertIn("Paginator(qs, 25)", src)
        assert_wires(
            self,
            "templates/siteconfig/partials/feature_control_audit_body.html",
            "components/pagination.html",
        )

    def test_feature_control_task_pagination_markers(self):
        assert_markup(
            self,
            "templates/siteconfig/feature_control_panel_content.html",
            FOLD_NAV,
            'data-rmc-scroll-policy="paginate"',
            "feature-cat-tabs",
        )

    def test_chrome_wires_collapsable_platform_wide(self):
        assert_renders(self, CHROME_STYLES, "rmc-collapsable.css")
        assert_renders(self, CHROME_SCRIPTS, "rmc-collapsable.js")

    def test_fold_js_compression_capabilities(self):
        # Static assets, not templates: nothing here reads a .html, so there is
        # no render for a mutation to remove.
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
        assert_markup(
            self,
            "templates/studio_os/modes/experience.html",
            "data-rmc-fold-stages",
            'data-rmc-fold-stage="builder"',
            'data-rmc-fold-stage="rollout"',
            'data-rmc-fold-stage="templates"',
            FOLD_NAV,
        )

    def test_cockpit_configure_fieldset_accordion(self):
        assert_markup(
            self,
            "templates/siteconfig/super/cockpit_configure.html",
            FIELDSET_ACCORDION,
            FOLD_NAV,
        )

    def test_theme_personality_fieldset_accordion(self):
        assert_markup(
            self,
            "templates/siteconfig/super/theme_personality_configure.html",
            FIELDSET_ACCORDION,
            FOLD_NAV,
        )

    def test_marketing_voice_fieldset_accordion(self):
        assert_markup(
            self,
            "templates/siteconfig/super/marketing_voice_configure.html",
            FIELDSET_ACCORDION,
            FOLD_NAV,
        )

    def test_tenant_app_catalog_fold_nav(self):
        assert_markup(
            self,
            "templates/marketplace/tenant_app_catalog.html",
            FOLD_NAV,
            'data-rmc-section-nav="auto"',
        )

    def test_migration_and_support_fold_residuals(self):
        assert_markup(self, "templates/migration_cloud/intake_new.html", FOLD_NAV)
        assert_markup(
            self, "templates/schools/super_support_ticket_detail.html", FOLD_NAV
        )
        assert_markup(
            self,
            "templates/migration_cloud/customer/intake_start.html",
            FIELDSET_ACCORDION,
            FOLD_NAV,
        )
