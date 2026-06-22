"""Phase-1 contract tests for the shared sidebar-intelligence engine.

The engine is a progressive-enhancement layer wired onto BOTH sidebars
(operator control-plane + tenant portal). These tests guard the wiring and the
cascade-driven on/off logic without a fragile full-partial render (the portal
sidebar pulls dozens of ``{% url %}`` targets; a NoReverseMatch there would be
noise, not signal). We assert:

  1. the exact ``{% if SITE.x == False %}`` attribute logic (default = on,
     explicit False = off) used to emit the contract attributes;
  2. both real nav-root templates emit the contract attributes;
  3. all three shells that own a sidebar load the engine script;
  4. the engine JS declares the behaviours it claims.
"""

from pathlib import Path

from django.template import Context, Template
from django.test import SimpleTestCase, TestCase

_ROOT = Path(__file__).resolve().parents[3]  # …/beta/school-management-system


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


class SidebarIntelligenceAttrLogicTests(SimpleTestCase):
    """The `{% if SITE.x == False %}0{% else %}1{% endif %}` cascade gate."""

    TPL = Template("{% if SITE.sidebar_intelligence == False %}0{% else %}1{% endif %}")

    def test_default_is_on(self):
        # No SITE in context -> undefined attr -> NOT == False -> "1" (on).
        self.assertEqual(self.TPL.render(Context({})), "1")

    def test_explicit_false_is_off(self):
        site = type("S", (), {"sidebar_intelligence": False})()
        self.assertEqual(self.TPL.render(Context({"SITE": site})), "0")

    def test_explicit_true_is_on(self):
        site = type("S", (), {"sidebar_intelligence": True})()
        self.assertEqual(self.TPL.render(Context({"SITE": site})), "1")

    def test_density_default(self):
        tpl = Template("{{ SITE.sidebar_density|default:'comfortable' }}")
        self.assertEqual(tpl.render(Context({})), "comfortable")
        site = type("S", (), {"sidebar_density": "compact"})()
        self.assertEqual(tpl.render(Context({"SITE": site})), "compact")


class SidebarIntelligenceWiringTests(SimpleTestCase):
    NAV_ROOTS = (
        "templates/partials/portal_sidebar.html",
        "templates/partials/control_plane_sidebar.html",
    )
    SHELLS = (
        "templates/control_plane_skeleton.html",
        "templates/portal_base.html",
        "templates/admin/base_site.html",
    )

    def test_both_nav_roots_emit_the_contract(self):
        for rel in self.NAV_ROOTS:
            src = _read(rel)
            self.assertIn("data-rmc-smart-sidebar=", src, rel)
            self.assertIn("data-rmc-sidebar-density=", src, rel)
            self.assertIn("data-rmc-sidebar-adaptive=", src, rel)
            self.assertIn("data-rmc-sidebar-search=", src, rel)

    def test_engine_script_loaded_in_every_sidebar_shell(self):
        for rel in self.SHELLS:
            self.assertIn("rmc-sidebar-intelligence.js", _read(rel), rel)

    def test_engine_js_declares_its_behaviours(self):
        js = _read("static/js/rmc-sidebar-intelligence.js")
        # attaches to the shared contract hook
        self.assertIn('data-rmc-smart-sidebar="1"', js)
        # both surface adapters are handled
        self.assertIn("control-plane", js)
        self.assertIn("cp-sidebar__item", js)
        self.assertIn("nav-link", js)
        # the four capability groups are present
        self.assertIn("rmc-sb-filter", js)        # type-to-filter
        self.assertIn("rmc-sb-frequent", js)       # adaptive band
        self.assertIn("data-rmc-density", js)      # density
        self.assertIn('addEventListener("keydown"', js)  # keyboard handling
        self.assertIn('"/"', js)                   # "/" focuses the filter

    def test_engine_css_grammar_defined(self):
        css = _read("static/css/rmc-class-grammar.css")
        for cls in (".rmc-sb-filter", ".rmc-sb-frequent", ".rmc-sb-mark", ".rmc-sb-cursor"):
            self.assertIn(cls, css, cls)


class SidebarLiveBadgeContractTests(SimpleTestCase):
    """Phase 2: live awareness badges, wired on both surfaces."""

    def test_engine_declares_live_badges(self):
        js = _read("static/js/rmc-sidebar-intelligence.js")
        self.assertIn("data-rmc-badge-poll", js)
        self.assertIn("rmc-sb-livebadge", js)
        self.assertIn("liveBadges", js)

    def test_both_nav_roots_poll_for_badges(self):
        for rel in (
            "templates/partials/portal_sidebar.html",
            "templates/partials/control_plane_sidebar.html",
        ):
            self.assertIn("data-rmc-badge-poll", _read(rel), rel)

    def test_livebadge_css_defined(self):
        css = _read("static/css/rmc-class-grammar.css")
        self.assertIn(".rmc-sb-livebadge", css)
        self.assertIn(".rmc-sb-has-livebadge", css)

    def test_both_badge_routes_registered(self):
        self.assertIn(
            'name="sidebar_badges"', _read("apps/siteconfig/urls.py")
        )
        self.assertIn(
            'name="sidebar_badges"', _read("apps/schools/super_urls.py")
        )


class SidebarBadgeEndpointTests(TestCase):
    """The endpoints fail soft to a well-formed payload (a badge poll must never
    error the shell)."""

    def test_operator_endpoint_shape(self):
        from django.test import RequestFactory

        from apps.schools.super_views_sidebar_badges import operator_sidebar_badges

        resp = operator_sidebar_badges(RequestFactory().get("/super/sidebar/badges/"))
        self.assertEqual(resp.status_code, 200)
        import json

        data = json.loads(resp.content)
        self.assertIn("badges", data)
        self.assertIn("interval", data)
        self.assertIsInstance(data["badges"], dict)
