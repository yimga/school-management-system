"""Contract + functional tests for the form-intelligence engine.

The engine (``static/js/rmc-form-intelligence.js``) auto-attaches to every real
``<form method="post">`` and orchestrates the unsaved-changes guard / save bar,
submit pending-state, character counters, blur-surfaced validation, and
long-form section nav — composing the existing rmc-form-dirty.js +
rmc-form-validation.js rather than duplicating them. Config is a SITE-cascade
(default-on, zero migration). Guards:

  1. cascade gate logic (default-on);
  2. the engine JS declares its capabilities + the attach contract + is CSP-safe;
  3. the config island + engine load on every authenticated shell;
  4. CSS grammar defined;
  5. the five cascade keys are write-whitelisted AND prefix-owned shadow keys;
  6. the admin settings route/view/template + registry action exist + gate;
  7. the school defaults round-trip through set_runtime_default + the façade.
"""

from pathlib import Path

from django.template import Context, Template
from django.test import SimpleTestCase, TestCase

_ROOT = Path(__file__).resolve().parents[3]


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


class FormCascadeGateTests(SimpleTestCase):
    TPL = Template("{% if SITE.form_intelligence == False %}false{% else %}true{% endif %}")

    def test_default_is_on(self):
        self.assertEqual(self.TPL.render(Context({})), "true")

    def test_explicit_false_is_off(self):
        site = type("S", (), {"form_intelligence": False})()
        self.assertEqual(self.TPL.render(Context({"SITE": site})), "false")


class FormEngineContractTests(SimpleTestCase):
    def test_engine_attaches_and_declares_capabilities(self):
        js = _read("static/js/rmc-form-intelligence.js")
        self.assertIn('querySelectorAll("form")', js)        # auto-attach to forms
        self.assertIn("data-rmc-form-enhance", js)            # opt-out hook
        self.assertIn("data-rmc-dirty-watch", js)             # composes (defers to) legacy lib
        self.assertIn("rmc-fi-savebar", js)                   # unsaved guard / save bar
        self.assertIn("aria-busy", js)                        # submit pending-state
        self.assertIn("rmc-fi-counter", js)                   # character counters
        self.assertIn("is-invalid", js)                       # blur-surfaced validation
        self.assertIn("rmc-fi-nav", js)                       # section nav

    def test_engine_render_is_csp_safe(self):
        js = _read("static/js/rmc-form-intelligence.js")
        self.assertIn("createElement", js)
        self.assertIn("textContent", js)
        self.assertNotIn(".innerHTML", js)

    def test_config_island_partial(self):
        tpl = _read("templates/partials/rmc_forms_engine.html")
        self.assertIn('id="rmc-forms-config"', tpl)
        self.assertIn("rmc-form-intelligence.js", tpl)
        self.assertIn("SITE.form_intelligence", tpl)

    def test_engine_loaded_on_every_authenticated_shell(self):
        for shell in (
            "templates/base.html",
            "templates/portal_base.html",
            "templates/control_plane_skeleton.html",
            "templates/admin/base_site.html",
        ):
            self.assertIn("partials/rmc_forms_engine.html", _read(shell), shell)

    def test_css_grammar_defined(self):
        css = _read("static/css/rmc-class-grammar.css")
        for cls in (".rmc-fi-savebar", ".rmc-fi-counter", ".rmc-fi-nav", ".rmc-fi-busy"):
            self.assertIn(cls, css, cls)

    def test_settings_route_template_and_action(self):
        urls = _read("apps/siteconfig/urls.py")
        self.assertIn('name="form_settings"', urls)
        self.assertIn("form_settings", _read("apps/siteconfig/command_bar_registry.py"))
        tpl = _read("templates/siteconfig/form_settings.html")
        for name in ("form_intelligence", "form_unsaved_guard", "form_pending", "form_validation", "form_section_nav"):
            self.assertIn(name, tpl, name)


class FormCascadeWiringTests(SimpleTestCase):
    KEYS = ("form_intelligence", "form_unsaved_guard", "form_pending", "form_validation", "form_section_nav")

    def test_write_keys_whitelisted(self):
        from apps.platform_runtime.runtime_defaults_first_class import _WIZARD_RUNTIME_DEFAULT_KEYS

        for key in self.KEYS:
            self.assertIn(key, _WIZARD_RUNTIME_DEFAULT_KEYS, key)

    def test_keys_are_prefix_owned_shadow_keys(self):
        from apps.siteconfig.domain_ownership import is_runtime_payload_shadow_key

        for key in ("form_intelligence", "form_section_nav"):
            self.assertTrue(is_runtime_payload_shadow_key(key), key)

    def test_can_manage_logic(self):
        from apps.siteconfig.views_forms import _can_manage_forms

        class _U:
            def __init__(self, su, perm):
                self.is_authenticated = True
                self.is_superuser = su
                self._perm = perm

            def has_feature_permission(self, p):
                return self._perm

        self.assertTrue(_can_manage_forms(_U(True, False)))
        self.assertTrue(_can_manage_forms(_U(False, True)))
        self.assertFalse(_can_manage_forms(_U(False, False)))
        self.assertFalse(_can_manage_forms(None))


class FormCascadeWriteTests(TestCase):
    def _school(self, tag):
        import uuid

        from apps.schools.models import School

        return School.objects.create(
            name="Form " + tag,
            slug=f"form{tag}-{uuid.uuid4().hex[:10]}",
            subdomain=f"form{tag}-{uuid.uuid4().hex[:10]}",
        )

    def test_set_persists_and_unknown_rejected(self):
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        school = self._school("p")
        self.assertTrue(set_runtime_default(school=school, field="form_pending", value=False))
        self.assertFalse(set_runtime_default(school=school, field="form_not_real", value=True))
        school.refresh_from_db()
        self.assertIs(school.settings.get("runtime_defaults", {}).get("form_pending"), False)

    def test_override_reads_back_through_facade(self):
        from django.core.cache import cache

        from apps.platform_runtime.helpers import get_effective_site_settings
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        school = self._school("r")
        set_runtime_default(school=school, field="form_validation", value=False)
        cache.clear()
        site = get_effective_site_settings(school=school)
        self.assertIs(getattr(site, "form_validation"), False)


class FormSettingsPostTests(TestCase):
    def test_post_writes_school_defaults(self):
        import uuid

        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.test import RequestFactory

        from apps.accounts.models import User
        from apps.schools.models import School
        from apps.siteconfig.views_forms import form_settings_view

        school = School.objects.create(
            name="Form UI",
            slug=f"formui-{uuid.uuid4().hex[:10]}",
            subdomain=f"formui-{uuid.uuid4().hex[:10]}",
        )
        admin = User.objects.create_user(username=f"forma-{uuid.uuid4().hex[:8]}@t.test", password="x")
        admin.is_superuser = True
        admin.save(update_fields=["is_superuser"])

        req = RequestFactory().post("/forms/settings/", {"form_unsaved_guard": "on"})
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        setattr(req, "_messages", FallbackStorage(req))
        req.user = admin
        req.school = school

        resp = form_settings_view(req)
        self.assertEqual(resp.status_code, 302)
        school.refresh_from_db()
        rd = (school.settings or {}).get("runtime_defaults", {})
        self.assertIs(rd.get("form_unsaved_guard"), True)
        self.assertIs(rd.get("form_intelligence"), False)   # checkbox omitted = off
        self.assertIs(rd.get("form_pending"), False)
        self.assertIs(rd.get("form_validation"), False)
        self.assertIs(rd.get("form_section_nav"), False)
