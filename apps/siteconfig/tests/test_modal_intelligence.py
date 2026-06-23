"""Contract + functional tests for the modal-intelligence engine (Surface 7).

The engine composes the existing native-<dialog> sheet system (window.RMCSheet
+ the .rmc-sheet grammar) and replaces the raw browser confirm()/alert() with a
styled, accessible confirm via a declarative [data-rmc-confirm] attribute and
the promise-returning window.RMCConfirm()/RMCAlert() API. Config is a SITE
cascade (default-on, zero migration). Guards:

  1. cascade gate logic (default-on);
  2. the engine declares its hooks, composes RMCSheet, + is CSP-safe;
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


class ModalCascadeGateTests(SimpleTestCase):
    TPL = Template("{% if SITE.modal_intelligence == False %}false{% else %}true{% endif %}")

    def test_default_is_on(self):
        self.assertEqual(self.TPL.render(Context({})), "true")

    def test_explicit_false_is_off(self):
        site = type("S", (), {"modal_intelligence": False})()
        self.assertEqual(self.TPL.render(Context({"SITE": site})), "false")


class ModalEngineContractTests(SimpleTestCase):
    def test_engine_declares_hooks_and_composes(self):
        js = _read("static/js/rmc-modal-intelligence.js")
        self.assertIn("data-rmc-confirm", js)        # declarative confirm hook
        self.assertIn("RMCConfirm", js)              # programmatic API
        self.assertIn("RMCAlert", js)                # alert replacement
        self.assertIn("RMCSheet", js)                # composes the sheet system
        self.assertIn("rmc-sheet", js)               # reuses the sheet grammar
        self.assertIn("dangerGuard", js)             # destructive-action guard

    def test_engine_is_csp_safe(self):
        js = _read("static/js/rmc-modal-intelligence.js")
        self.assertIn("createElement", js)
        self.assertIn("textContent", js)
        self.assertNotIn(".innerHTML", js)

    def test_config_island_partial(self):
        tpl = _read("templates/partials/rmc_modal_engine.html")
        self.assertIn('id="rmc-modal-config"', tpl)
        self.assertIn("rmc-modal-intelligence.js", tpl)
        self.assertIn("SITE.modal_intelligence", tpl)

    def test_engine_loaded_on_every_authenticated_shell(self):
        for shell in (
            "templates/base.html",
            "templates/portal_base.html",
            "templates/control_plane_skeleton.html",
            "templates/admin/base_site.html",
        ):
            self.assertIn("partials/rmc_modal_engine.html", _read(shell), shell)

    def test_css_grammar_defined(self):
        css = _read("static/css/rmc-class-grammar.css")
        for cls in (".rmc-confirm", ".rmc-confirm__icon"):
            self.assertIn(cls, css, cls)

    def test_settings_route_template_and_action(self):
        urls = _read("apps/siteconfig/urls.py")
        self.assertIn('name="modal_settings"', urls)
        self.assertIn("modal_settings", _read("apps/siteconfig/command_bar_registry.py"))
        tpl = _read("templates/siteconfig/modal_settings.html")
        for name in ("modal_intelligence", "modal_confirm", "modal_danger_guard"):
            self.assertIn(name, tpl, name)


class ModalCascadeWiringTests(SimpleTestCase):
    KEYS = ("modal_intelligence", "modal_confirm", "modal_danger_guard")

    def test_write_keys_whitelisted(self):
        from apps.platform_runtime.runtime_defaults_first_class import _WIZARD_RUNTIME_DEFAULT_KEYS

        for key in self.KEYS:
            self.assertIn(key, _WIZARD_RUNTIME_DEFAULT_KEYS, key)

    def test_keys_are_prefix_owned_shadow_keys(self):
        from apps.siteconfig.domain_ownership import is_runtime_payload_shadow_key

        for key in ("modal_intelligence", "modal_confirm"):
            self.assertTrue(is_runtime_payload_shadow_key(key), key)

    def test_can_manage_logic(self):
        from apps.siteconfig.views_modals_engine import _can_manage_modals

        class _U:
            def __init__(self, su, perm):
                self.is_authenticated = True
                self.is_superuser = su
                self._perm = perm

            def has_feature_permission(self, p):
                return self._perm

        self.assertTrue(_can_manage_modals(_U(True, False)))
        self.assertTrue(_can_manage_modals(_U(False, True)))
        self.assertFalse(_can_manage_modals(_U(False, False)))
        self.assertFalse(_can_manage_modals(None))


class ModalCascadeWriteTests(TestCase):
    def _school(self, tag):
        import uuid

        from apps.schools.models import School

        return School.objects.create(
            name="Modal " + tag,
            slug=f"modal{tag}-{uuid.uuid4().hex[:10]}",
            subdomain=f"modal{tag}-{uuid.uuid4().hex[:10]}",
        )

    def test_set_persists_and_unknown_rejected(self):
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        school = self._school("p")
        self.assertTrue(
            set_runtime_default(school=school, field="modal_confirm", value=False)
        )
        self.assertFalse(
            set_runtime_default(school=school, field="modal_not_real", value=True)
        )
        school.refresh_from_db()
        self.assertIs(
            school.settings.get("runtime_defaults", {}).get("modal_confirm"), False
        )

    def test_override_reads_back_through_facade(self):
        from django.core.cache import cache

        from apps.platform_runtime.helpers import get_effective_site_settings
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        school = self._school("r")
        set_runtime_default(school=school, field="modal_danger_guard", value=False)
        cache.clear()
        site = get_effective_site_settings(school=school)
        self.assertIs(getattr(site, "modal_danger_guard"), False)


class ModalSettingsPostTests(TestCase):
    def test_post_writes_school_defaults(self):
        import uuid

        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.test import RequestFactory

        from apps.accounts.models import User
        from apps.schools.models import School
        from apps.siteconfig.views_modals_engine import modal_settings_view

        school = School.objects.create(
            name="Modal UI",
            slug=f"modalui-{uuid.uuid4().hex[:10]}",
            subdomain=f"modalui-{uuid.uuid4().hex[:10]}",
        )
        admin = User.objects.create_user(
            username=f"modala-{uuid.uuid4().hex[:8]}@t.test", password="x"
        )
        admin.is_superuser = True
        admin.save(update_fields=["is_superuser"])

        req = RequestFactory().post("/modals/settings/", {"modal_confirm": "on"})
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        setattr(req, "_messages", FallbackStorage(req))
        req.user = admin
        req.school = school

        resp = modal_settings_view(req)
        self.assertEqual(resp.status_code, 302)
        school.refresh_from_db()
        rd = (school.settings or {}).get("runtime_defaults", {})
        self.assertIs(rd.get("modal_confirm"), True)
        self.assertIs(rd.get("modal_intelligence"), False)  # checkbox omitted = off
        self.assertIs(rd.get("modal_danger_guard"), False)
