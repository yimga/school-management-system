"""Contract + functional tests for the detail-intelligence engine (Surface 8).

The engine composes the existing key-value grammar (.rmc-kv) + the section-nav
observer (rmc-section-nav.js). It enhances detail/profile field values in place
(copy-to-clipboard, mailto:/tel:, em-dash for empties) and auto-fills an
author-placed section nav. Config is a SITE cascade (default-on, zero migration).
Guards:

  1. cascade gate logic (default-on);
  2. the engine declares its hooks, composes the grammar, + is CSP-safe;
  3. the config island + engine load on every authenticated shell;
  4. CSS grammar defined;
  5. the five cascade keys are write-whitelisted AND prefix-owned shadow keys;
  6. the admin settings route/view/template + registry action exist;
  7. the school defaults round-trip through set_runtime_default + the façade.
"""

from pathlib import Path

from django.template import Context, Template
from django.test import SimpleTestCase, TestCase

_ROOT = Path(__file__).resolve().parents[3]


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


class DetailCascadeGateTests(SimpleTestCase):
    TPL = Template("{% if SITE.detail_intelligence == False %}false{% else %}true{% endif %}")

    def test_default_is_on(self):
        self.assertEqual(self.TPL.render(Context({})), "true")

    def test_explicit_false_is_off(self):
        site = type("S", (), {"detail_intelligence": False})()
        self.assertEqual(self.TPL.render(Context({"SITE": site})), "false")


class DetailEngineContractTests(SimpleTestCase):
    def test_engine_declares_hooks_and_composes(self):
        js = _read("static/js/rmc-detail-intelligence.js")
        self.assertIn("rmc-kv", js)                  # composes the kv grammar
        self.assertIn("data-rmc-field", js)          # field hook
        self.assertIn("data-rmc-copy", js)           # explicit copy hook
        self.assertIn("data-rmc-section-anchor", js) # composes section anchors
        self.assertIn("data-rmc-section-nav-auto", js)  # author-placed mount
        self.assertIn("rmc-detail-copy", js)         # copy affordance
        self.assertIn("mailto:", js)                 # actionable contacts
        self.assertIn("rmc-detail-empty", js)        # em-dash for empties

    def test_engine_is_csp_safe(self):
        js = _read("static/js/rmc-detail-intelligence.js")
        self.assertIn("createElement", js)
        self.assertIn("textContent", js)
        self.assertNotIn(".innerHTML", js)

    def test_config_island_partial(self):
        tpl = _read("templates/partials/rmc_detail_engine.html")
        self.assertIn('id="rmc-detail-config"', tpl)
        self.assertIn("rmc-detail-intelligence.js", tpl)
        self.assertIn("SITE.detail_intelligence", tpl)

    def test_engine_loaded_on_every_authenticated_shell(self):
        for shell in (
            "templates/base.html",
            "templates/portal_base.html",
            "templates/control_plane_skeleton.html",
            "templates/admin/base_site.html",
        ):
            self.assertIn("partials/rmc_detail_engine.html", _read(shell), shell)

    def test_css_grammar_defined(self):
        css = _read("static/css/rmc-class-grammar.css")
        for cls in (".rmc-detail-copy", ".rmc-detail-action", ".rmc-detail-empty"):
            self.assertIn(cls, css, cls)

    def test_settings_route_template_and_action(self):
        urls = _read("apps/siteconfig/urls.py")
        self.assertIn('name="detail_settings"', urls)
        self.assertIn("detail_settings", _read("apps/siteconfig/command_bar_registry.py"))
        tpl = _read("templates/siteconfig/detail_settings.html")
        for name in (
            "detail_intelligence",
            "detail_copy",
            "detail_actionable",
            "detail_empty_fields",
            "detail_section_nav",
        ):
            self.assertIn(name, tpl, name)


class DetailCascadeWiringTests(SimpleTestCase):
    KEYS = (
        "detail_intelligence",
        "detail_copy",
        "detail_actionable",
        "detail_empty_fields",
        "detail_section_nav",
    )

    def test_write_keys_whitelisted(self):
        from apps.platform_runtime.runtime_defaults_first_class import _WIZARD_RUNTIME_DEFAULT_KEYS

        for key in self.KEYS:
            self.assertIn(key, _WIZARD_RUNTIME_DEFAULT_KEYS, key)

    def test_keys_are_prefix_owned_shadow_keys(self):
        from apps.siteconfig.domain_ownership import is_runtime_payload_shadow_key

        for key in ("detail_intelligence", "detail_copy"):
            self.assertTrue(is_runtime_payload_shadow_key(key), key)

    def test_can_manage_logic(self):
        from apps.siteconfig.views_detail_engine import _can_manage_detail

        class _U:
            def __init__(self, su, perm):
                self.is_authenticated = True
                self.is_superuser = su
                self._perm = perm

            def has_feature_permission(self, p):
                return self._perm

        self.assertTrue(_can_manage_detail(_U(True, False)))
        self.assertTrue(_can_manage_detail(_U(False, True)))
        self.assertFalse(_can_manage_detail(_U(False, False)))
        self.assertFalse(_can_manage_detail(None))


class DetailCascadeWriteTests(TestCase):
    def _school(self, tag):
        import uuid

        from apps.schools.models import School

        return School.objects.create(
            name="Detail " + tag,
            slug=f"detl{tag}-{uuid.uuid4().hex[:10]}",
            subdomain=f"detl{tag}-{uuid.uuid4().hex[:10]}",
        )

    def test_set_persists_and_unknown_rejected(self):
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        school = self._school("p")
        self.assertTrue(
            set_runtime_default(school=school, field="detail_copy", value=False)
        )
        self.assertFalse(
            set_runtime_default(school=school, field="detail_not_real", value=True)
        )
        school.refresh_from_db()
        self.assertIs(
            school.settings.get("runtime_defaults", {}).get("detail_copy"), False
        )

    def test_override_reads_back_through_facade(self):
        from django.core.cache import cache

        from apps.platform_runtime.helpers import get_effective_site_settings
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        school = self._school("r")
        set_runtime_default(school=school, field="detail_section_nav", value=False)
        cache.clear()
        site = get_effective_site_settings(school=school)
        self.assertIs(getattr(site, "detail_section_nav"), False)


class DetailSettingsPostTests(TestCase):
    def test_post_writes_school_defaults(self):
        import uuid

        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.test import RequestFactory

        from apps.accounts.models import User
        from apps.schools.models import School
        from apps.siteconfig.views_detail_engine import detail_settings_view

        school = School.objects.create(
            name="Detail UI",
            slug=f"detlui-{uuid.uuid4().hex[:10]}",
            subdomain=f"detlui-{uuid.uuid4().hex[:10]}",
        )
        admin = User.objects.create_user(
            username=f"detla-{uuid.uuid4().hex[:8]}@t.test", password="x"
        )
        admin.is_superuser = True
        admin.save(update_fields=["is_superuser"])

        req = RequestFactory().post("/detail/settings/", {"detail_copy": "on"})
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        setattr(req, "_messages", FallbackStorage(req))
        req.user = admin
        req.school = school

        resp = detail_settings_view(req)
        self.assertEqual(resp.status_code, 302)
        school.refresh_from_db()
        rd = (school.settings or {}).get("runtime_defaults", {})
        self.assertIs(rd.get("detail_copy"), True)
        self.assertIs(rd.get("detail_intelligence"), False)  # checkbox omitted = off
        self.assertIs(rd.get("detail_section_nav"), False)
