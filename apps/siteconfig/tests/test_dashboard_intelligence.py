"""Contract + functional tests for the dashboard-intelligence engine.

The engine attaches to the existing [data-rmc-tp-dashboard-cockpit] grid and
personalizes the cockpit sections per-user (reorder/hide/density/focus). Prefs
are SERVER-PERSISTED into the existing DashboardUserPreference.dashboard_layout
JSONField (no migration), with a localStorage write-through cache. Guards:

  1. cascade gate logic (default-on);
  2. the engine JS declares its capabilities + the attach contract;
  3. the config island + engine load on every authenticated shell;
  4. CSS grammar defined;
  5. the four cascade keys are write-whitelisted AND prefix-owned shadow keys;
  6. the prefs endpoint round-trips into the existing model (no migration);
  7. the admin settings route/view/template + registry action exist + gate.
"""

import json
from pathlib import Path

from django.template import Context, Template
from django.test import SimpleTestCase, TestCase

_ROOT = Path(__file__).resolve().parents[3]


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


class DashCascadeGateTests(SimpleTestCase):
    TPL = Template("{% if SITE.dashboard_intelligence == False %}false{% else %}true{% endif %}")

    def test_default_is_on(self):
        self.assertEqual(self.TPL.render(Context({})), "true")

    def test_explicit_false_is_off(self):
        site = type("S", (), {"dashboard_intelligence": False})()
        self.assertEqual(self.TPL.render(Context({"SITE": site})), "false")


class DashEngineContractTests(SimpleTestCase):
    def test_engine_attaches_and_declares_capabilities(self):
        js = _read("static/js/rmc-dashboard-intelligence.js")
        self.assertIn("data-rmc-tp-dashboard-cockpit", js)   # attach hook
        self.assertIn("rmc-collapsable", js)                  # operates on existing sections
        self.assertIn("rmc-dash-grip", js)                    # reorder
        self.assertIn("rmc-dash-hidden", js)                  # hide/show
        self.assertIn("data-rmc-dash-density", js)            # density
        self.assertIn("rmc-dash-focus", js)                   # adaptive focus band
        self.assertIn("prefs_url", js)                        # server persistence
        self.assertIn("fetch(", js)

    def test_engine_render_is_csp_safe(self):
        js = _read("static/js/rmc-dashboard-intelligence.js")
        self.assertIn("createElement", js)
        self.assertIn("textContent", js)
        self.assertNotIn(".innerHTML", js)

    def test_config_island_partial(self):
        tpl = _read("templates/partials/rmc_dashboard_engine.html")
        self.assertIn('id="rmc-dashboard-config"', tpl)
        self.assertIn("rmc-dashboard-intelligence.js", tpl)
        self.assertIn("SITE.dashboard_intelligence", tpl)
        self.assertIn("dashboard_prefs", tpl)

    def test_engine_loaded_on_every_authenticated_shell(self):
        for shell in (
            "templates/base.html",
            "templates/portal_base.html",
            "templates/control_plane_skeleton.html",
            "templates/admin/base_site.html",
        ):
            self.assertIn("partials/rmc_dashboard_engine.html", _read(shell), shell)

    def test_css_grammar_defined(self):
        css = _read("static/css/rmc-class-grammar.css")
        for cls in (".rmc-dash-bar", ".rmc-dash-focus", ".rmc-dash-grip", ".rmc-dash-hidden", ".rmc-dash-cust"):
            self.assertIn(cls, css, cls)

    def test_settings_route_template_and_action(self):
        urls = _read("apps/siteconfig/urls.py")
        self.assertIn('name="dashboard_prefs"', urls)
        self.assertIn('name="dashboard_settings"', urls)
        self.assertIn("dashboard_settings", _read("apps/siteconfig/command_bar_registry.py"))
        tpl = _read("templates/siteconfig/dashboard_settings.html")
        for name in ("dashboard_intelligence", "dashboard_reorder", "dashboard_adaptive", "dashboard_density"):
            self.assertIn(name, tpl, name)


class DashCascadeWiringTests(SimpleTestCase):
    def test_write_keys_whitelisted(self):
        from apps.platform_runtime.runtime_defaults_first_class import _WIZARD_RUNTIME_DEFAULT_KEYS

        for key in ("dashboard_intelligence", "dashboard_reorder", "dashboard_adaptive", "dashboard_density"):
            self.assertIn(key, _WIZARD_RUNTIME_DEFAULT_KEYS, key)

    def test_keys_are_prefix_owned_shadow_keys(self):
        from apps.siteconfig.domain_ownership import is_runtime_payload_shadow_key

        for key in ("dashboard_intelligence", "dashboard_density"):
            self.assertTrue(is_runtime_payload_shadow_key(key), key)

    def test_can_manage_logic(self):
        from apps.siteconfig.views_dashboard_prefs import _can_manage_dashboard

        class _U:
            def __init__(self, su, perm):
                self.is_authenticated = True
                self.is_superuser = su
                self._perm = perm

            def has_feature_permission(self, p):
                return self._perm

        self.assertTrue(_can_manage_dashboard(_U(True, False)))
        self.assertTrue(_can_manage_dashboard(_U(False, True)))
        self.assertFalse(_can_manage_dashboard(_U(False, False)))
        self.assertFalse(_can_manage_dashboard(None))


class DashPrefsEndpointTests(TestCase):
    """Per-user prefs round-trip into the EXISTING DashboardUserPreference model."""

    def _user(self):
        import uuid

        from apps.accounts.models import User

        return User.objects.create_user(username=f"dash-{uuid.uuid4().hex[:8]}@t.test", password="x")

    def test_post_then_get_roundtrips(self):
        from django.test import RequestFactory

        from apps.siteconfig.models_dashboard import DashboardUserPreference
        from apps.siteconfig.views_dashboard_prefs import dashboard_prefs_view

        user = self._user()
        body = json.dumps({
            "surface": "backend-admin",
            "density": "compact",
            "hidden": ["backend__lesson_of_day"],
            "order": ["backend__today_snapshot", "backend__quick_actions_grid"],
        })
        req = RequestFactory().post("/dashboard/prefs/", data=body, content_type="application/json")
        req.user = user
        resp = dashboard_prefs_view(req)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(json.loads(resp.content)["ok"])

        # persisted into the existing JSONField under the reserved namespace
        pref = DashboardUserPreference.objects.get(user=user)
        bucket = pref.dashboard_layout["_rmc_cockpit_sections"]["backend-admin"]
        self.assertEqual(bucket["density"], "compact")
        self.assertEqual(bucket["hidden"], ["backend__lesson_of_day"])

        # GET reads it back
        getreq = RequestFactory().get("/dashboard/prefs/?surface=backend-admin")
        getreq.user = user
        getresp = dashboard_prefs_view(getreq)
        data = json.loads(getresp.content)
        self.assertEqual(data["prefs"]["density"], "compact")
        self.assertEqual(data["prefs"]["order"], ["backend__today_snapshot", "backend__quick_actions_grid"])

    def test_bad_density_coerced(self):
        from django.test import RequestFactory

        from apps.siteconfig.views_dashboard_prefs import dashboard_prefs_view

        user = self._user()
        req = RequestFactory().post("/dashboard/prefs/", data=json.dumps({"surface": "x", "density": "ginormous"}), content_type="application/json")
        req.user = user
        dashboard_prefs_view(req)
        getreq = RequestFactory().get("/dashboard/prefs/?surface=x")
        getreq.user = user
        self.assertEqual(json.loads(dashboard_prefs_view(getreq).content)["prefs"]["density"], "comfortable")


class DashCascadeWriteTests(TestCase):
    def _school(self, tag):
        import uuid

        from apps.schools.models import School

        return School.objects.create(
            name="Dash " + tag,
            slug=f"dash{tag}-{uuid.uuid4().hex[:10]}",
            subdomain=f"dash{tag}-{uuid.uuid4().hex[:10]}",
        )

    def test_set_density_persists_and_unknown_rejected(self):
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        school = self._school("p")
        self.assertTrue(set_runtime_default(school=school, field="dashboard_density", value="spacious"))
        self.assertFalse(set_runtime_default(school=school, field="dashboard_not_real", value=True))
        school.refresh_from_db()
        self.assertEqual(school.settings.get("runtime_defaults", {}).get("dashboard_density"), "spacious")

    def test_override_reads_back_through_facade(self):
        from django.core.cache import cache

        from apps.platform_runtime.helpers import get_effective_site_settings
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        school = self._school("r")
        set_runtime_default(school=school, field="dashboard_reorder", value=False)
        cache.clear()
        site = get_effective_site_settings(school=school)
        self.assertIs(getattr(site, "dashboard_reorder"), False)


class DashSettingsPostTests(TestCase):
    def test_post_writes_school_defaults(self):
        import uuid

        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.test import RequestFactory

        from apps.accounts.models import User
        from apps.schools.models import School
        from apps.siteconfig.views_dashboard_prefs import dashboard_settings_view

        school = School.objects.create(
            name="Dash UI",
            slug=f"dashui-{uuid.uuid4().hex[:10]}",
            subdomain=f"dashui-{uuid.uuid4().hex[:10]}",
        )
        admin = User.objects.create_user(username=f"dasha-{uuid.uuid4().hex[:8]}@t.test", password="x")
        admin.is_superuser = True
        admin.save(update_fields=["is_superuser"])

        req = RequestFactory().post(
            "/dashboard/settings/",
            {"dashboard_reorder": "on", "dashboard_density": "spacious"},
        )
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        setattr(req, "_messages", FallbackStorage(req))
        req.user = admin
        req.school = school

        resp = dashboard_settings_view(req)
        self.assertEqual(resp.status_code, 302)
        school.refresh_from_db()
        rd = (school.settings or {}).get("runtime_defaults", {})
        self.assertIs(rd.get("dashboard_reorder"), True)
        self.assertEqual(rd.get("dashboard_density"), "spacious")
        self.assertIs(rd.get("dashboard_intelligence"), False)  # checkbox omitted = off
        self.assertIs(rd.get("dashboard_adaptive"), False)
