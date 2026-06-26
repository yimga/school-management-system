"""Contract + functional tests for the empty-state intelligence engine (Surface 4).

Two TABLE empty states ride rmc-table-intelligence.js (filter-to-zero + zero-
data); ad-hoc adoption rides rmc-empty-intelligence.js; the first-run welcome
card becomes progress-aware. Config is a SITE cascade (default-on, zero
migration). The 3 deprecated empty variants (cp_empty / tp_empty /
world_class_empty_state) were retired once every caller migrated to the
canonical component. Guards:

  1. cascade gate logic (default-on);
  2. the table engine owns both table empty states + is CSP-safe;
  3. the adopt engine + config island + load on every authenticated shell;
  4. CSS grammar defined;
  5. the five cascade keys are write-whitelisted AND prefix-owned shadow keys;
  6. the admin settings route/view/template + registry action exist;
  7. deprecated variants are retired + no template still includes them;
  8. the first-run card is progress-aware (server + template);
  9. the school defaults round-trip through set_runtime_default + the façade.
"""

from pathlib import Path

from django.template import Context, Template
from django.test import SimpleTestCase, TestCase

_ROOT = Path(__file__).resolve().parents[3]


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


class EmptyCascadeGateTests(SimpleTestCase):
    TPL = Template("{% if SITE.empty_intelligence == False %}false{% else %}true{% endif %}")

    def test_default_is_on(self):
        self.assertEqual(self.TPL.render(Context({})), "true")

    def test_explicit_false_is_off(self):
        site = type("S", (), {"empty_intelligence": False})()
        self.assertEqual(self.TPL.render(Context({"SITE": site})), "false")


class EmptyEngineContractTests(SimpleTestCase):
    def test_table_engine_owns_both_table_empty_states(self):
        js = _read("static/js/rmc-table-intelligence.js")
        self.assertIn("rmc-empty-config", js)        # reads the empty cascade
        self.assertIn("table_filter", js)
        self.assertIn("table_data", js)
        self.assertIn("rmc-tbl-empty-row", js)
        self.assertIn("rmc-empty--row", js)          # canonical empty grammar
        self.assertIn("Clear filter", js)            # filter-empty CTA
        self.assertIn("Nothing here yet", js)        # data-empty title

    def test_table_engine_excludes_empty_rows_from_ops(self):
        js = _read("static/js/rmc-table-intelligence.js")
        # bodyRows must skip the injected empty row (else filter/sort/count break)
        self.assertIn('contains("rmc-tbl-empty-row")', js)

    def test_adopt_engine_is_csp_safe(self):
        js = _read("static/js/rmc-empty-intelligence.js")
        self.assertIn("data-rmc-empty", js)
        self.assertIn("createElement", js)
        self.assertIn("textContent", js)
        self.assertNotIn(".innerHTML", js)

    def test_config_island_partial(self):
        tpl = _read("templates/partials/rmc_empty_engine.html")
        self.assertIn('id="rmc-empty-config"', tpl)
        self.assertIn("rmc-empty-intelligence.js", tpl)
        self.assertIn("SITE.empty_intelligence", tpl)

    def test_engine_loaded_on_every_authenticated_shell(self):
        for shell in (
            "templates/base.html",
            "templates/portal_base.html",
            "templates/control_plane_skeleton.html",
            "templates/admin/base_site.html",
        ):
            self.assertIn("partials/rmc_empty_engine.html", _read(shell), shell)

    def test_css_grammar_defined(self):
        css = _read("static/css/rmc-class-grammar.css")
        for cls in (".rmc-tbl-empty-row", ".rmc-empty__term"):
            self.assertIn(cls, css, cls)

    def test_settings_route_template_and_action(self):
        urls = _read("apps/siteconfig/urls.py")
        self.assertIn('name="empty_settings"', urls)
        self.assertIn("empty_settings", _read("apps/siteconfig/command_bar_registry.py"))
        tpl = _read("templates/siteconfig/empty_settings.html")
        for name in ("empty_intelligence", "empty_table_filter", "empty_table_data", "empty_adopt", "empty_first_run"):
            self.assertIn(name, tpl, name)

    def test_deprecated_variants_are_retired(self):
        # The 3 deprecated shims (cp_empty / tp_empty / world_class_empty_state)
        # were retired once every caller was migrated to the canonical component.
        for variant in ("cp_empty.html", "tp_empty.html", "world_class_empty_state.html"):
            self.assertFalse(
                (_ROOT / "templates" / "components" / variant).exists(),
                f"{variant} should be deleted — callers must include rmc_empty_state.html directly",
            )

    def test_no_template_includes_retired_empty_variants(self):
        offenders = []
        for tpl in (_ROOT / "templates").rglob("*.html"):
            text = tpl.read_text(encoding="utf-8", errors="replace")
            for variant in ("components/cp_empty.html", "components/tp_empty.html",
                            "components/world_class_empty_state.html"):
                if variant in text:
                    offenders.append(f"{tpl}: {variant}")
        self.assertEqual(offenders, [], f"retired empty-state shims still included: {offenders}")

    def test_first_run_card_is_progress_aware(self):
        src = _read("apps/dashboard/first_run_zero_state.py")
        self.assertIn("progress_percent", src)
        self.assertIn("empty_first_run", src)
        self.assertIn("get_school_onboarding_progress", src)
        self.assertIn("data-rmc-first-run-progress", _read("templates/portal_base.html"))


class EmptyCascadeWiringTests(SimpleTestCase):
    KEYS = ("empty_intelligence", "empty_table_filter", "empty_table_data", "empty_adopt", "empty_first_run")

    def test_write_keys_whitelisted(self):
        from apps.platform_runtime.runtime_defaults_first_class import _WIZARD_RUNTIME_DEFAULT_KEYS

        for key in self.KEYS:
            self.assertIn(key, _WIZARD_RUNTIME_DEFAULT_KEYS, key)

    def test_keys_are_prefix_owned_shadow_keys(self):
        from apps.siteconfig.domain_ownership import is_runtime_payload_shadow_key

        for key in ("empty_intelligence", "empty_first_run"):
            self.assertTrue(is_runtime_payload_shadow_key(key), key)

    def test_can_manage_logic(self):
        from apps.siteconfig.views_empty import _can_manage_empty

        class _U:
            def __init__(self, su, perm):
                self.is_authenticated = True
                self.is_superuser = su
                self._perm = perm

            def has_feature_permission(self, p):
                return self._perm

        self.assertTrue(_can_manage_empty(_U(True, False)))
        self.assertTrue(_can_manage_empty(_U(False, True)))
        self.assertFalse(_can_manage_empty(_U(False, False)))
        self.assertFalse(_can_manage_empty(None))


class EmptyCascadeWriteTests(TestCase):
    def _school(self, tag):
        import uuid

        from apps.schools.models import School

        return School.objects.create(
            name="Empty " + tag,
            slug=f"empty{tag}-{uuid.uuid4().hex[:10]}",
            subdomain=f"empty{tag}-{uuid.uuid4().hex[:10]}",
        )

    def test_set_persists_and_unknown_rejected(self):
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        school = self._school("p")
        self.assertTrue(set_runtime_default(school=school, field="empty_table_filter", value=False))
        self.assertFalse(set_runtime_default(school=school, field="empty_not_real", value=True))
        school.refresh_from_db()
        self.assertIs(school.settings.get("runtime_defaults", {}).get("empty_table_filter"), False)

    def test_override_reads_back_through_facade(self):
        from django.core.cache import cache

        from apps.platform_runtime.helpers import get_effective_site_settings
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        school = self._school("r")
        set_runtime_default(school=school, field="empty_table_data", value=False)
        cache.clear()
        site = get_effective_site_settings(school=school)
        self.assertIs(getattr(site, "empty_table_data"), False)


class EmptySettingsPostTests(TestCase):
    def test_post_writes_school_defaults(self):
        import uuid

        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.test import RequestFactory

        from apps.accounts.models import User
        from apps.schools.models import School
        from apps.siteconfig.views_empty import empty_settings_view

        school = School.objects.create(
            name="Empty UI",
            slug=f"emptyui-{uuid.uuid4().hex[:10]}",
            subdomain=f"emptyui-{uuid.uuid4().hex[:10]}",
        )
        admin = User.objects.create_user(username=f"emptya-{uuid.uuid4().hex[:8]}@t.test", password="x")
        admin.is_superuser = True
        admin.save(update_fields=["is_superuser"])

        req = RequestFactory().post("/empty-states/settings/", {"empty_table_filter": "on"})
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        setattr(req, "_messages", FallbackStorage(req))
        req.user = admin
        req.school = school

        resp = empty_settings_view(req)
        self.assertEqual(resp.status_code, 302)
        school.refresh_from_db()
        rd = (school.settings or {}).get("runtime_defaults", {})
        self.assertIs(rd.get("empty_table_filter"), True)
        self.assertIs(rd.get("empty_intelligence"), False)   # checkbox omitted = off
        self.assertIs(rd.get("empty_table_data"), False)
        self.assertIs(rd.get("empty_adopt"), False)
        self.assertIs(rd.get("empty_first_run"), False)
