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


class SidebarPreferencesContractTests(SimpleTestCase):
    """Phase 3: per-user preferences popover (client-side) + cascade write-key."""

    def test_engine_declares_prefs_popover(self):
        js = _read("static/js/rmc-sidebar-intelligence.js")
        self.assertIn("rmc-sb-prefs", js)
        self.assertIn("rmcSidebarPrefs", js)         # localStorage key
        self.assertIn("applyVisibility", js)         # toggle re-apply
        self.assertIn("prefBool", js)                # user-pref-over-cascade

    def test_prefs_popover_css_defined(self):
        css = _read("static/css/rmc-class-grammar.css")
        for cls in (".rmc-sb-prefs", ".rmc-sb-prefs__seg-btn", ".rmc-sb-filter__prefs"):
            self.assertIn(cls, css, cls)

    def test_cascade_write_keys_whitelisted(self):
        from apps.platform_runtime.runtime_defaults_first_class import (
            _WIZARD_RUNTIME_DEFAULT_KEYS,
        )

        for key in (
            "sidebar_intelligence",
            "sidebar_search",
            "sidebar_adaptive_order",
            "sidebar_density",
        ):
            self.assertIn(key, _WIZARD_RUNTIME_DEFAULT_KEYS, key)


class SidebarCascadeWriteTests(TestCase):
    """set_runtime_default persists a per-tenant sidebar default (no migration)."""

    def test_set_sidebar_density_persists(self):
        import uuid

        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default
        from apps.schools.models import School

        school = School.objects.create(
            name="Sidebar Cfg",
            slug=f"sbcfg-{uuid.uuid4().hex[:10]}",
            subdomain=f"sbcfg-{uuid.uuid4().hex[:10]}",
        )
        changed = set_runtime_default(school=school, field="sidebar_density", value="compact")
        self.assertTrue(changed)
        school.refresh_from_db()
        self.assertEqual(
            school.settings.get("runtime_defaults", {}).get("sidebar_density"), "compact"
        )

    def test_unknown_field_is_rejected(self):
        import uuid

        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default
        from apps.schools.models import School

        school = School.objects.create(
            name="Sidebar Cfg2",
            slug=f"sbcfg2-{uuid.uuid4().hex[:10]}",
            subdomain=f"sbcfg2-{uuid.uuid4().hex[:10]}",
        )
        self.assertFalse(
            set_runtime_default(school=school, field="not_a_real_sidebar_key", value="x")
        )


class SidebarConfigUIContractTests(SimpleTestCase):
    """Admin 'set school default' config surface (isolated from the monolithic form)."""

    def test_engine_declares_config_link(self):
        js = _read("static/js/rmc-sidebar-intelligence.js")
        self.assertIn("data-rmc-sidebar-config-url", js)
        self.assertIn("rmc-sb-prefs__link", js)

    def test_settings_route_and_template_exist(self):
        self.assertIn('name="sidebar_settings"', _read("apps/siteconfig/urls.py"))
        # template renders the four controls
        tpl = _read("templates/siteconfig/sidebar_settings.html")
        for name in ("sidebar_intelligence", "sidebar_search", "sidebar_adaptive_order", "sidebar_density"):
            self.assertIn(name, tpl, name)

    def test_can_manage_logic(self):
        from apps.siteconfig.views_sidebar import _can_manage_sidebar

        class _U:
            def __init__(self, su, perm):
                self.is_authenticated = True
                self.is_superuser = su
                self._perm = perm

            def has_feature_permission(self, p):
                return self._perm

        self.assertTrue(_can_manage_sidebar(_U(True, False)))
        self.assertTrue(_can_manage_sidebar(_U(False, True)))
        self.assertFalse(_can_manage_sidebar(_U(False, False)))
        self.assertFalse(_can_manage_sidebar(None))


class SidebarConfigPostTests(TestCase):
    """POST persists the school defaults via set_runtime_default."""

    def test_post_writes_school_defaults(self):
        import uuid

        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.test import RequestFactory

        from apps.accounts.models import User
        from apps.schools.models import School
        from apps.siteconfig.views_sidebar import sidebar_settings_view

        school = School.objects.create(
            name="Sidebar UI",
            slug=f"sbui-{uuid.uuid4().hex[:10]}",
            subdomain=f"sbui-{uuid.uuid4().hex[:10]}",
        )
        admin = User.objects.create_user(username=f"a-{uuid.uuid4().hex[:8]}@t.test", password="x")
        admin.is_superuser = True
        admin.save(update_fields=["is_superuser"])

        req = RequestFactory().post(
            "/sidebar/settings/",
            {"sidebar_intelligence": "on", "sidebar_search": "on", "sidebar_density": "compact"},
        )
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        setattr(req, "_messages", FallbackStorage(req))
        req.user = admin
        req.school = school

        resp = sidebar_settings_view(req)
        self.assertEqual(resp.status_code, 302)
        school.refresh_from_db()
        rd = (school.settings or {}).get("runtime_defaults", {})
        self.assertEqual(rd.get("sidebar_density"), "compact")
        self.assertTrue(rd.get("sidebar_intelligence"))
        self.assertFalse(rd.get("sidebar_adaptive_order"))  # checkbox omitted = off
