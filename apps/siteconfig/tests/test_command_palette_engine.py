"""Contract + functional tests for the unified ⌘K command-palette engine.

The palette is now the single command ENGINE bound to ⌘K platform-wide
(rmc-command-bar.js yields wherever #rmc-cmdk is mounted). It federates the
server registry + the rendered sidebar + page-aware/AI sources into one fuzzy,
adaptive, CSP-safe list, and is configurable through the SITE cascade with no
migration. These tests guard:

  1. the cascade gate logic (default-on; explicit False off);
  2. the engine JS declares its unify + federation + intelligence behaviours;
  3. rmc-command-bar.js yields its keybinding to the engine;
  4. the template emits the contract attributes + the registry URL;
  5. the CSS grammar for the new affordances is defined;
  6. the four cascade keys are write-whitelisted AND prefix-owned (so a per-
     tenant override actually reads back through the façade — the real bug);
  7. the admin settings route/view/template exist and gate correctly.
"""

from pathlib import Path

from django.template import Context, Template
from django.test import SimpleTestCase, TestCase

_ROOT = Path(__file__).resolve().parents[3]  # …/beta/school-management-system


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


class PaletteCascadeGateTests(SimpleTestCase):
    TPL = Template("{% if SITE.command_palette_intelligence == False %}0{% else %}1{% endif %}")

    def test_default_is_on(self):
        self.assertEqual(self.TPL.render(Context({})), "1")

    def test_explicit_false_is_off(self):
        site = type("S", (), {"command_palette_intelligence": False})()
        self.assertEqual(self.TPL.render(Context({"SITE": site})), "0")

    def test_explicit_true_is_on(self):
        site = type("S", (), {"command_palette_intelligence": True})()
        self.assertEqual(self.TPL.render(Context({"SITE": site})), "1")


class PaletteEngineContractTests(SimpleTestCase):
    def test_engine_unifies_and_federates(self):
        js = _read("static/js/rmc-command-palette.js")
        # absorbs the server registry (the formerly-separate command bar)
        self.assertIn("fetchRegistry", js)
        self.assertIn("actions_url", js)
        # federates the rendered sidebar DOM, CSP-safe
        self.assertIn("harvestSidebar", js)
        self.assertIn("data-sidebar-nav", js)
        # source chips for federation legibility
        self.assertIn("rmc-cmdk__src", js)

    def test_engine_has_intelligence(self):
        js = _read("static/js/rmc-command-palette.js")
        self.assertIn("USAGE_KEY", js)         # frequency
        self.assertIn("PINNED_KEY", js)        # pinning
        self.assertIn("togglePin", js)
        self.assertIn("cfg.fuzzy", js)         # fuzzy toggle honored
        self.assertIn("rmc-cmdk__mark", js)    # match highlight
        self.assertIn("rmc-cmdk__band", js)    # adaptive bands

    def test_engine_render_is_csp_safe(self):
        js = _read("static/js/rmc-command-palette.js")
        self.assertIn("createElement", js)
        self.assertIn("textContent", js)
        # the old innerHTML-string item render is gone (we build nodes now)
        self.assertNotIn("li.innerHTML", js)

    def test_command_bar_yields_to_engine(self):
        js = _read("static/js/rmc-command-bar.js")
        self.assertIn('getElementById("rmc-cmdk")', js)
        self.assertIn("yielded", js)

    def test_engine_mounted_on_every_authenticated_shell(self):
        # Platform-wide: the engine must be on ALL authenticated root shells, not
        # a subset. (marketing/base_marketing is public/pre-auth → intentionally
        # excluded.) base.html is a standalone root (the others don't extend it),
        # so it needs its own include.
        for shell in (
            "templates/base.html",
            "templates/portal_base.html",
            "templates/control_plane_skeleton.html",
            "templates/admin/base_site.html",
        ):
            self.assertIn("components/rmc_command_palette.html", _read(shell), shell)

    def test_template_emits_contract(self):
        tpl = _read("templates/components/rmc_command_palette.html")
        for attr in (
            "data-rmc-cmdk-enabled",
            "data-rmc-cmdk-fuzzy",
            "data-rmc-cmdk-adaptive",
            "data-rmc-cmdk-federate-sidebar",
        ):
            self.assertIn(attr, tpl, attr)
        self.assertIn("actions_url", tpl)
        self.assertIn("command_bar_actions", tpl)

    def test_engine_supports_search_scroll_contract(self):
        js = _read("static/js/rmc-command-palette.js")
        self.assertIn("reloadCatalog", js)
        self.assertIn("scrollListToTop", js)
        self.assertIn("isOpen", js)
        self.assertIn('e.key === "/"', js)

    def test_scroll_css_contract(self):
        css = _read("static/css/rmc-long-page-grammar.css")
        self.assertIn(".rmc-cmdk__list", css)
        self.assertIn("overflow-y: auto", css)
        self.assertIn("min-height: 0", css)
        self.assertIn("flex-shrink: 0", css)

    def test_shortcuts_yield_when_cmdk_open(self):
        js = _read("static/js/rmc-shortcuts-runtime.js")
        self.assertIn("isCmdkOpen", js)
        self.assertIn("rmc-cmdk-open", js)
        self.assertIn("isTypingTarget(e.target)", js)
        self.assertIn("openCommandPalette", js)

    def test_copilot_yields_ctrl_k_to_palette(self):
        js = _read("static/js/_pages/rmc-copilot-rail.js")
        self.assertIn('getElementById("rmc-cmdk")', js)

    def test_manager_nav_json_no_trailing_comma_block(self):
        tpl = _read("templates/components/rmc_command_palette.html")
        self.assertNotIn('"keywords": "search help faq articles"},', tpl)
        self.assertIn('"keywords": "search help faq articles"}', tpl)
        self.assertIn("{% if request.public_host_kind == 'manager' and cmdk_help_analytics_url %},{", tpl)

    def test_search_kbd_chips_open_palette(self):
        for path in (
            "templates/portal_base.html",
            "templates/partials/manager_operator_topbar.html",
            "templates/components/admin_nav_bridge.html",
        ):
            html = _read(path)
            self.assertIn("data-rmc-cmdk-open", html, path)

    def test_palette_trigger_delegate(self):
        js = _read("static/js/rmc-command-palette.js")
        self.assertIn("[data-rmc-cmdk-trigger]", js)

    def test_css_grammar_defined(self):
        css = _read("static/css/rmc-class-grammar.css")
        for cls in (".rmc-cmdk__band", ".rmc-cmdk__mark", ".rmc-cmdk__src", ".rmc-cmdk__pin"):
            self.assertIn(cls, css, cls)

    def test_settings_route_and_template_exist(self):
        self.assertIn('name="command_palette_settings"', _read("apps/siteconfig/urls.py"))
        tpl = _read("templates/siteconfig/command_palette_settings.html")
        for name in (
            "command_palette_intelligence",
            "command_palette_fuzzy",
            "command_palette_adaptive",
            "command_palette_federate_sidebar",
        ):
            self.assertIn(name, tpl, name)

    def test_palette_surfaces_its_own_settings_action(self):
        self.assertIn("command_palette_settings", _read("apps/siteconfig/command_bar_registry.py"))


class PaletteCascadeWiringTests(SimpleTestCase):
    def test_write_keys_whitelisted(self):
        from apps.platform_runtime.runtime_defaults_first_class import (
            _WIZARD_RUNTIME_DEFAULT_KEYS,
        )

        for key in (
            "command_palette_intelligence",
            "command_palette_fuzzy",
            "command_palette_adaptive",
            "command_palette_federate_sidebar",
        ):
            self.assertIn(key, _WIZARD_RUNTIME_DEFAULT_KEYS, key)

    def test_keys_are_prefix_owned_shadow_keys(self):
        # This is what makes hasattr(resolved, key) True so a per-tenant override
        # actually applies in get_effective_site_settings (the latent-bug guard).
        from apps.siteconfig.domain_ownership import is_runtime_payload_shadow_key

        for key in (
            "command_palette_intelligence",
            "command_palette_fuzzy",
            "command_palette_adaptive",
            "command_palette_federate_sidebar",
        ):
            self.assertTrue(is_runtime_payload_shadow_key(key), key)

    def test_can_manage_logic(self):
        from apps.siteconfig.views_command_palette import _can_manage_command_palette

        class _U:
            def __init__(self, su, perm):
                self.is_authenticated = True
                self.is_superuser = su
                self._perm = perm

            def has_feature_permission(self, p):
                return self._perm

        self.assertTrue(_can_manage_command_palette(_U(True, False)))
        self.assertTrue(_can_manage_command_palette(_U(False, True)))
        self.assertFalse(_can_manage_command_palette(_U(False, False)))
        self.assertFalse(_can_manage_command_palette(None))


class PaletteCascadeWriteTests(TestCase):
    def _school(self, tag):
        import uuid

        from apps.schools.models import School

        return School.objects.create(
            name="CP " + tag,
            slug=f"cp{tag}-{uuid.uuid4().hex[:10]}",
            subdomain=f"cp{tag}-{uuid.uuid4().hex[:10]}",
        )

    def test_set_persists(self):
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        school = self._school("p")
        self.assertTrue(set_runtime_default(school=school, field="command_palette_fuzzy", value=False))
        school.refresh_from_db()
        self.assertIs(
            school.settings.get("runtime_defaults", {}).get("command_palette_fuzzy"), False
        )

    def test_unknown_field_rejected(self):
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        school = self._school("u")
        self.assertFalse(set_runtime_default(school=school, field="command_palette_not_real", value=True))

    def test_override_reads_back_through_facade(self):
        """The whole point of the prefix owner: an override must take effect."""
        from django.core.cache import cache

        from apps.platform_runtime.helpers import get_effective_site_settings
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        school = self._school("r")
        set_runtime_default(school=school, field="command_palette_fuzzy", value=False)
        cache.clear()
        site = get_effective_site_settings(school=school)
        self.assertIs(getattr(site, "command_palette_fuzzy"), False)


class PaletteSettingsPostTests(TestCase):
    def test_post_writes_school_defaults(self):
        import uuid

        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.test import RequestFactory

        from apps.accounts.models import User
        from apps.schools.models import School
        from apps.siteconfig.views_command_palette import command_palette_settings_view

        school = School.objects.create(
            name="CP UI",
            slug=f"cpui-{uuid.uuid4().hex[:10]}",
            subdomain=f"cpui-{uuid.uuid4().hex[:10]}",
        )
        admin = User.objects.create_user(username=f"cpa-{uuid.uuid4().hex[:8]}@t.test", password="x")
        admin.is_superuser = True
        admin.save(update_fields=["is_superuser"])

        # fuzzy + federate ON; adaptive + intelligence omitted (= off)
        req = RequestFactory().post(
            "/command-palette/settings/",
            {"command_palette_fuzzy": "on", "command_palette_federate_sidebar": "on"},
        )
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        setattr(req, "_messages", FallbackStorage(req))
        req.user = admin
        req.school = school

        resp = command_palette_settings_view(req)
        self.assertEqual(resp.status_code, 302)
        school.refresh_from_db()
        rd = (school.settings or {}).get("runtime_defaults", {})
        self.assertIs(rd.get("command_palette_fuzzy"), True)
        self.assertIs(rd.get("command_palette_federate_sidebar"), True)
        self.assertIs(rd.get("command_palette_adaptive"), False)  # checkbox omitted = off
        self.assertIs(rd.get("command_palette_intelligence"), False)
