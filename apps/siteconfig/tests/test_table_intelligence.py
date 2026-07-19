"""Contract + functional tests for the shared table-intelligence engine.

The engine auto-attaches to every ``table.rmc-data-table`` already on the page
(377+ templates) — platform-wide with zero per-page edits — and adds instant
filter, click-to-sort, column show/hide, per-user density, keyboard nav, and CSV
export, configured through the SITE cascade with no migration. Guards:

  1. the cascade gate logic (default-on);
  2. the engine JS declares its capabilities + the auto-attach contract;
  3. the config island + engine load on EVERY authenticated shell;
  4. the CSS grammar is defined;
  5. the six cascade keys are write-whitelisted AND prefix-owned (override reads
     back through the façade);
  6. the admin settings route/view/template exist and gate correctly.
"""

from pathlib import Path

from django.template import Context, Template
from django.test import SimpleTestCase, TestCase

_ROOT = Path(__file__).resolve().parents[3]  # …/beta/school-management-system


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


class TableCascadeGateTests(SimpleTestCase):
    TPL = Template("{% if SITE.table_intelligence == False %}false{% else %}true{% endif %}")

    def test_default_is_on(self):
        self.assertEqual(self.TPL.render(Context({})), "true")

    def test_explicit_false_is_off(self):
        site = type("S", (), {"table_intelligence": False})()
        self.assertEqual(self.TPL.render(Context({"SITE": site})), "false")


class TableEngineContractTests(SimpleTestCase):
    def test_engine_auto_attaches_and_opts_out(self):
        js = _read("static/js/rmc-table-intelligence.js")
        self.assertIn("table.rmc-data-table", js)     # auto-attach to existing class
        self.assertIn("data-rmc-smart-table", js)     # opt-out hook
        self.assertIn("rmc-tables-config", js)        # cascade config island

    def test_engine_declares_capabilities(self):
        js = _read("static/js/rmc-table-intelligence.js")
        self.assertIn("aria-sort", js)                # click-to-sort
        self.assertIn("rmc-tbl-mark", js)             # filter highlight
        self.assertIn("rmc-tbl-col-hidden", js)       # column show/hide
        self.assertIn("data-density", js)             # density
        self.assertIn("exportCsv", js)                # CSV export
        self.assertIn("ArrowDown", js)                # keyboard nav

    def test_engine_render_is_csp_safe(self):
        js = _read("static/js/rmc-table-intelligence.js")
        self.assertIn("createElement", js)
        self.assertIn("textContent", js)
        self.assertNotIn(".innerHTML", js)

    def test_config_island_partial(self):
        tpl = _read("templates/partials/rmc_tables_engine.html")
        self.assertIn('id="rmc-tables-config"', tpl)
        self.assertIn("rmc-table-intelligence.js", tpl)
        self.assertIn("SITE.table_intelligence", tpl)

    def test_engine_loaded_on_every_authenticated_shell(self):
        for shell in (
            "templates/base.html",
            "templates/portal_base.html",
            "templates/control_plane_skeleton.html",
            "templates/admin/base_site.html",
        ):
            self.assertIn("partials/rmc_tables_engine.html", _read(shell), shell)

    def test_css_grammar_defined(self):
        css = _read("static/css/rmc-class-grammar.css")
        for cls in (".rmc-tbl-bar", ".rmc-tbl-seg", ".rmc-tbl-mark", ".rmc-tbl-sortable", ".rmc-tbl-cur"):
            self.assertIn(cls, css, cls)

    def test_density_css_honors_compact_cozy_roomy(self):
        """Intelligence writes compact|comfortable|spacious — CSS must respond."""
        long_page = _read("static/css/rmc-long-page-grammar.css")
        table_sys = _read("static/css/table-system.css")
        for src, label in ((long_page, "long-page"), (table_sys, "table-system")):
            for val in ('[data-density="compact"]', '[data-density="comfortable"]', '[data-density="spacious"]'):
                self.assertIn(val, src, f"{label} missing {val}")
        # Legacy aliases kept so older markup still densifies
        self.assertIn('[data-density="condensed"]', long_page)
        self.assertIn('[data-density="expanded"]', long_page)

    def test_engine_apply_density_helper(self):
        js = _read("static/js/rmc-table-intelligence.js")
        self.assertIn("function applyDensity", js)
        self.assertIn("function normalizeDensity", js)
        self.assertIn("table-density-", js)
        self.assertIn('condensed: "compact"', js)
        self.assertIn('expanded: "spacious"', js)
        # Density bar is not trapped behind the min-rows extras gate alone
        self.assertIn("showExtras", js)
        self.assertIn("wantExtras", js)

    def test_settings_route_template_and_action(self):
        self.assertIn('name="table_settings"', _read("apps/siteconfig/urls.py"))
        self.assertIn("table_settings", _read("apps/siteconfig/command_bar_registry.py"))
        tpl = _read("templates/siteconfig/table_settings.html")
        for name in ("table_intelligence", "table_filter", "table_sort", "table_columns", "table_export", "table_density"):
            self.assertIn(name, tpl, name)


class TableCascadeWiringTests(SimpleTestCase):
    def test_write_keys_whitelisted(self):
        from apps.platform_runtime.runtime_defaults_first_class import _WIZARD_RUNTIME_DEFAULT_KEYS

        for key in ("table_intelligence", "table_filter", "table_sort", "table_columns", "table_export", "table_density"):
            self.assertIn(key, _WIZARD_RUNTIME_DEFAULT_KEYS, key)

    def test_keys_are_prefix_owned_shadow_keys(self):
        from apps.siteconfig.domain_ownership import is_runtime_payload_shadow_key

        for key in ("table_intelligence", "table_filter", "table_density"):
            self.assertTrue(is_runtime_payload_shadow_key(key), key)

    def test_can_manage_logic(self):
        from apps.siteconfig.views_tables import _can_manage_tables

        class _U:
            def __init__(self, su, perm):
                self.is_authenticated = True
                self.is_superuser = su
                self._perm = perm

            def has_feature_permission(self, p):
                return self._perm

        self.assertTrue(_can_manage_tables(_U(True, False)))
        self.assertTrue(_can_manage_tables(_U(False, True)))
        self.assertFalse(_can_manage_tables(_U(False, False)))
        self.assertFalse(_can_manage_tables(None))


class TableCascadeWriteTests(TestCase):
    def _school(self, tag):
        import uuid

        from apps.schools.models import School

        return School.objects.create(
            name="Tbl " + tag,
            slug=f"tbl{tag}-{uuid.uuid4().hex[:10]}",
            subdomain=f"tbl{tag}-{uuid.uuid4().hex[:10]}",
        )

    def test_set_density_persists(self):
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        school = self._school("p")
        self.assertTrue(set_runtime_default(school=school, field="table_density", value="compact"))
        school.refresh_from_db()
        self.assertEqual(school.settings.get("runtime_defaults", {}).get("table_density"), "compact")

    def test_unknown_field_rejected(self):
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        school = self._school("u")
        self.assertFalse(set_runtime_default(school=school, field="table_not_real", value=True))

    def test_override_reads_back_through_facade(self):
        from django.core.cache import cache

        from apps.platform_runtime.helpers import get_effective_site_settings
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        school = self._school("r")
        set_runtime_default(school=school, field="table_sort", value=False)
        cache.clear()
        site = get_effective_site_settings(school=school)
        self.assertIs(getattr(site, "table_sort"), False)


class TableSettingsPostTests(TestCase):
    def test_post_writes_school_defaults(self):
        import uuid

        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.test import RequestFactory

        from apps.accounts.models import User
        from apps.schools.models import School
        from apps.siteconfig.views_tables import table_settings_view

        school = School.objects.create(
            name="Tbl UI",
            slug=f"tblui-{uuid.uuid4().hex[:10]}",
            subdomain=f"tblui-{uuid.uuid4().hex[:10]}",
        )
        admin = User.objects.create_user(username=f"tbla-{uuid.uuid4().hex[:8]}@t.test", password="x")
        admin.is_superuser = True
        admin.save(update_fields=["is_superuser"])

        req = RequestFactory().post(
            "/tables/settings/",
            {"table_filter": "on", "table_sort": "on", "table_density": "compact"},
        )
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        setattr(req, "_messages", FallbackStorage(req))
        req.user = admin
        req.school = school

        resp = table_settings_view(req)
        self.assertEqual(resp.status_code, 302)
        school.refresh_from_db()
        rd = (school.settings or {}).get("runtime_defaults", {})
        self.assertIs(rd.get("table_filter"), True)
        self.assertIs(rd.get("table_sort"), True)
        self.assertEqual(rd.get("table_density"), "compact")
        self.assertIs(rd.get("table_columns"), False)  # checkbox omitted = off
