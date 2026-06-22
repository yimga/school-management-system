"""Contract + functional tests for the loading-intelligence engine (Surface 5).

The engine composes the existing top progress bar (rmc-page-progress.js) +
skeleton grammar + form submit pending-state, and closes the gaps: action
pending-state for non-form buttons/links ([data-rmc-loading] + auto a[download])
and skeleton-on-load for HTMX targets ([data-rmc-skeleton]). Config is a SITE
cascade (default-on, zero migration). Guards:

  1. cascade gate logic (default-on);
  2. the engine declares its hooks, composes the progress bar, + is CSP-safe;
  3. the config island + engine load on every authenticated shell;
  4. CSS grammar defined;
  5. the three cascade keys are write-whitelisted AND prefix-owned shadow keys;
  6. the admin settings route/view/template + registry action exist;
  7. the school defaults round-trip through set_runtime_default + the façade.
"""

from pathlib import Path

from django.template import Context, Template
from django.test import SimpleTestCase, TestCase

_ROOT = Path(__file__).resolve().parents[3]


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


class LoadingCascadeGateTests(SimpleTestCase):
    TPL = Template("{% if SITE.loading_intelligence == False %}false{% else %}true{% endif %}")

    def test_default_is_on(self):
        self.assertEqual(self.TPL.render(Context({})), "true")

    def test_explicit_false_is_off(self):
        site = type("S", (), {"loading_intelligence": False})()
        self.assertEqual(self.TPL.render(Context({"SITE": site})), "false")


class LoadingEngineContractTests(SimpleTestCase):
    def test_engine_declares_hooks_and_composes(self):
        js = _read("static/js/rmc-loading-intelligence.js")
        self.assertIn("data-rmc-loading", js)        # action opt-in hook
        self.assertIn("a[download]", js)             # auto download links
        self.assertIn("rmc-loading-busy", js)        # spinner class
        self.assertIn("data-rmc-skeleton", js)       # skeleton-on-load hook
        self.assertIn("htmx:beforeRequest", js)      # ties into HTMX
        self.assertIn("RMCPageProgress", js)         # composes the existing top bar
        self.assertIn("RMCLoading", js)              # public helper

    def test_skips_form_submits(self):
        # form submits are owned by rmc-form-intelligence.js; the loading engine
        # must not double-handle them.
        js = _read("static/js/rmc-loading-intelligence.js")
        self.assertIn("isFormSubmit", js)

    def test_engine_is_csp_safe(self):
        js = _read("static/js/rmc-loading-intelligence.js")
        self.assertIn("createElement", js)
        self.assertIn("textContent", js)
        self.assertNotIn(".innerHTML", js)

    def test_config_island_partial(self):
        tpl = _read("templates/partials/rmc_loading_engine.html")
        self.assertIn('id="rmc-loading-config"', tpl)
        self.assertIn("rmc-loading-intelligence.js", tpl)
        self.assertIn("SITE.loading_intelligence", tpl)

    def test_engine_loaded_on_every_authenticated_shell(self):
        for shell in (
            "templates/base.html",
            "templates/portal_base.html",
            "templates/control_plane_skeleton.html",
            "templates/admin/base_site.html",
        ):
            self.assertIn("partials/rmc_loading_engine.html", _read(shell), shell)

    def test_css_grammar_defined(self):
        css = _read("static/css/rmc-class-grammar.css")
        for cls in (".rmc-loading-busy", ".rmc-loading-skeleton"):
            self.assertIn(cls, css, cls)

    def test_settings_route_template_and_action(self):
        urls = _read("apps/siteconfig/urls.py")
        self.assertIn('name="loading_settings"', urls)
        self.assertIn("loading_settings", _read("apps/siteconfig/command_bar_registry.py"))
        tpl = _read("templates/siteconfig/loading_settings.html")
        for name in ("loading_intelligence", "loading_actions", "loading_skeletons"):
            self.assertIn(name, tpl, name)


class LoadingCascadeWiringTests(SimpleTestCase):
    KEYS = ("loading_intelligence", "loading_actions", "loading_skeletons")

    def test_write_keys_whitelisted(self):
        from apps.platform_runtime.runtime_defaults_first_class import _WIZARD_RUNTIME_DEFAULT_KEYS

        for key in self.KEYS:
            self.assertIn(key, _WIZARD_RUNTIME_DEFAULT_KEYS, key)

    def test_keys_are_prefix_owned_shadow_keys(self):
        from apps.siteconfig.domain_ownership import is_runtime_payload_shadow_key

        for key in ("loading_intelligence", "loading_skeletons"):
            self.assertTrue(is_runtime_payload_shadow_key(key), key)

    def test_can_manage_logic(self):
        from apps.siteconfig.views_loading import _can_manage_loading

        class _U:
            def __init__(self, su, perm):
                self.is_authenticated = True
                self.is_superuser = su
                self._perm = perm

            def has_feature_permission(self, p):
                return self._perm

        self.assertTrue(_can_manage_loading(_U(True, False)))
        self.assertTrue(_can_manage_loading(_U(False, True)))
        self.assertFalse(_can_manage_loading(_U(False, False)))
        self.assertFalse(_can_manage_loading(None))


class LoadingCascadeWriteTests(TestCase):
    def _school(self, tag):
        import uuid

        from apps.schools.models import School

        return School.objects.create(
            name="Loading " + tag,
            slug=f"load{tag}-{uuid.uuid4().hex[:10]}",
            subdomain=f"load{tag}-{uuid.uuid4().hex[:10]}",
        )

    def test_set_persists_and_unknown_rejected(self):
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        school = self._school("p")
        self.assertTrue(set_runtime_default(school=school, field="loading_actions", value=False))
        self.assertFalse(set_runtime_default(school=school, field="loading_not_real", value=True))
        school.refresh_from_db()
        self.assertIs(school.settings.get("runtime_defaults", {}).get("loading_actions"), False)

    def test_override_reads_back_through_facade(self):
        from django.core.cache import cache

        from apps.platform_runtime.helpers import get_effective_site_settings
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        school = self._school("r")
        set_runtime_default(school=school, field="loading_skeletons", value=False)
        cache.clear()
        site = get_effective_site_settings(school=school)
        self.assertIs(getattr(site, "loading_skeletons"), False)


class LoadingSettingsPostTests(TestCase):
    def test_post_writes_school_defaults(self):
        import uuid

        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.test import RequestFactory

        from apps.accounts.models import User
        from apps.schools.models import School
        from apps.siteconfig.views_loading import loading_settings_view

        school = School.objects.create(
            name="Loading UI",
            slug=f"loadui-{uuid.uuid4().hex[:10]}",
            subdomain=f"loadui-{uuid.uuid4().hex[:10]}",
        )
        admin = User.objects.create_user(username=f"loada-{uuid.uuid4().hex[:8]}@t.test", password="x")
        admin.is_superuser = True
        admin.save(update_fields=["is_superuser"])

        req = RequestFactory().post("/loading/settings/", {"loading_actions": "on"})
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        setattr(req, "_messages", FallbackStorage(req))
        req.user = admin
        req.school = school

        resp = loading_settings_view(req)
        self.assertEqual(resp.status_code, 302)
        school.refresh_from_db()
        rd = (school.settings or {}).get("runtime_defaults", {})
        self.assertIs(rd.get("loading_actions"), True)
        self.assertIs(rd.get("loading_intelligence"), False)   # checkbox omitted = off
        self.assertIs(rd.get("loading_skeletons"), False)
