"""New-tenant Setup-Wizards index polish + RBAC gate (no DB).

Covers the 2026-06-16 fixes for the "New Test High School" first-run defects:

* The completion banner no longer prints a raw ``mfa_setup`` slug (humanized).
* The wizard search index now carries a humanized ``label`` so the client
  never paints a raw ``wizards.*`` slug in the dropdown.
* The flat A→Z wizard list is grouped into labeled category sections.
* The tenant wizard RBAC gate no longer over-permits operator-only wizards to
  tenant admins.

All source-level / pure-function assertions — no DB, no live request cycle.
"""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

from apps.setup_studio import wizard_categories, wizard_engine
from apps.setup_studio.wizard_analytics import build_wizard_search_index
from apps.setup_studio.wizard_labels import humanize_wizard_token

# tests/ -> setup_studio/ -> apps/ -> <repo root: school-management-system/>
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[3]
_APP_ROOT = _REPO_ROOT / "apps" / "setup_studio"
_TEMPLATES = _REPO_ROOT / "templates" / "setup_studio"


class CompletionBannerHumanizationTests(SimpleTestCase):
    def setUp(self):
        wizard_engine.load_wizard_registry()

    def test_template_humanizes_just_completed_key(self):
        tpl = (_TEMPLATES / "tenant_wizard_index.html").read_text(encoding="utf-8")
        # The raw `{{ wizard_key }} complete.` form is gone; the value is piped
        # through the humanizer.
        self.assertNotIn("with wizard_key=just_completed_wizard_key %}", tpl)
        self.assertIn(
            "just_completed_wizard_key|humanize_wizard_token",
            tpl,
        )

    def test_view_passes_label_not_raw_key_to_banner(self):
        # humanize_wizard_token leaves a bare key ("mfa_setup") UNCHANGED, so the
        # banner would still print the slug if the view passed wizard.wizard_key.
        # The view must hand the banner wizard.label_token instead.
        src = (_APP_ROOT / "wizard_views.py").read_text(encoding="utf-8")
        self.assertNotIn('"just_completed_wizard_key": wizard.wizard_key', src)
        self.assertIn('"just_completed_wizard_key": wizard.label_token', src)

    def test_mfa_setup_banner_reads_as_friendly_label(self):
        # The exact screenshot string "mfa_setup complete." must NOT appear:
        # the banner receives mfa_setup's label_token, humanized.
        mfa = wizard_engine.WIZARD_REGISTRY["mfa_setup"]
        banner_title = humanize_wizard_token(mfa.label_token)
        self.assertTrue(banner_title)
        self.assertNotEqual(banner_title, "mfa_setup")
        self.assertFalse(banner_title.startswith("wizards."))
        # Bare-key sanity: confirms WHY the raw-key path was broken.
        self.assertEqual(humanize_wizard_token("mfa_setup"), "mfa_setup")


class SearchIndexLabelTests(SimpleTestCase):
    def setUp(self):
        wizard_engine.load_wizard_registry()

    def test_every_search_entry_carries_humanized_label(self):
        index = build_wizard_search_index(wizard_engine.WIZARD_REGISTRY.values())
        self.assertTrue(index)
        for entry in index:
            self.assertIn("label", entry)
            self.assertTrue(entry["label"])
            # A humanized label never leaks a synthesized slug namespace.
            self.assertFalse(entry["label"].startswith("wizards."))

    def test_search_js_prefers_humanized_label(self):
        js = (
            _REPO_ROOT
            / "static" / "js" / "_pages" / "rmc-wizard-search.js"
        ).read_text(encoding="utf-8")
        self.assertIn("entry.label || entry.label_token", js)


class CategoryGroupingTests(SimpleTestCase):
    def setUp(self):
        wizard_engine.load_wizard_registry()

    def test_tenant_admin_wizards_group_into_ordered_sections(self):
        wizards = wizard_engine.list_wizards_for_audience("tenant_admin")
        groups = wizard_categories.group_wizards_by_category(wizards)
        self.assertTrue(groups, "expected at least one category section")
        # Sections follow CATEGORY_ORDER and are non-empty.
        seen_order = [g["key"] for g in groups]
        canonical = [k for k in wizard_categories.CATEGORY_ORDER if k in seen_order]
        self.assertEqual(seen_order, canonical)
        for g in groups:
            self.assertTrue(g["wizards"])
            self.assertTrue(g["label"])

    def test_grouping_preserves_every_wizard(self):
        wizards = wizard_engine.list_wizards_for_audience("tenant_admin")
        groups = wizard_categories.group_wizards_by_category(wizards)
        grouped_keys = {w.wizard_key for g in groups for w in g["wizards"]}
        self.assertEqual(grouped_keys, {w.wizard_key for w in wizards})

    def test_unknown_key_falls_into_default_bucket(self):
        self.assertEqual(
            wizard_categories.category_for("a_wizard_that_does_not_exist"),
            wizard_categories.DEFAULT_CATEGORY,
        )


class WizardRbacGateTests(SimpleTestCase):
    """The tenant wizard gate must not admit operator-only wizards to admins."""

    def setUp(self):
        wizard_engine.load_wizard_registry()

    def test_operator_only_wizards_exist_in_registry(self):
        operator_only = [
            w.wizard_key
            for w in wizard_engine.WIZARD_REGISTRY.values()
            if tuple(w.audience) == ("operator",)
        ]
        # These are the platform/operator break-glass flows that must never be
        # reachable by a plain tenant admin.
        for key in ("super_create_school", "self_healing_observability_guard"):
            self.assertIn(key, operator_only)

    def test_gate_source_drops_operator_or_clause(self):
        src = (_APP_ROOT / "wizard_views.py").read_text(encoding="utf-8")
        # The over-permitting clause is gone.
        self.assertNotIn(
            'if "tenant_admin" in wizard.audience or "operator" in wizard.audience:',
            src,
        )
        # The tenant-admin branch now gates on tenant_admin audience only.
        self.assertIn('if "tenant_admin" in wizard.audience:', src)


class WizardSearchAudienceRbacTests(SimpleTestCase):
    """The wizard search API must not let a non-operator enumerate operator-only
    wizard metadata via a client-supplied ?audience= param (RBAC tightening)."""

    def setUp(self):
        wizard_engine.load_wizard_registry()

    def _search(self, *, is_staff, own_audience, audience_param="operator"):
        import json
        from types import SimpleNamespace
        from unittest import mock

        from django.test import RequestFactory

        from apps.setup_studio.views_activation_dashboard import WizardSearchAPIView

        req = RequestFactory().get("/x/wizard-search/", {"audience": audience_param})
        req.user = SimpleNamespace(is_authenticated=True, is_staff=is_staff)
        with mock.patch(
            "apps.setup_studio.wizard_views._user_audience",
            return_value=own_audience,
        ):
            resp = WizardSearchAPIView.as_view()(req)
        return json.loads(resp.content)

    def test_non_operator_cannot_enumerate_operator_wizards(self):
        data = self._search(is_staff=False, own_audience="tenant_admin")
        keys = {r.get("wizard_key") for r in data["results"]}
        self.assertNotIn("super_create_school", keys)
        for r in data["results"]:
            self.assertIn("tenant_admin", r["audience"])

    def test_operator_staff_can_enumerate_operator_wizards(self):
        data = self._search(is_staff=True, own_audience="operator")
        keys = {r.get("wizard_key") for r in data["results"]}
        self.assertIn("super_create_school", keys)

    def test_unresolved_audience_returns_empty(self):
        data = self._search(is_staff=False, own_audience=None)
        self.assertEqual(data["count"], 0)


class LifecycleStageTaxonomyTests(SimpleTestCase):
    """The taxonomy is the 4-stage onboarding lifecycle, numbered 1..4."""

    def setUp(self):
        wizard_engine.load_wizard_registry()

    def test_category_order_is_the_four_lifecycle_stages(self):
        self.assertEqual(
            wizard_categories.CATEGORY_ORDER,
            ("get_started", "configure", "operate", "govern"),
        )

    def test_every_stage_carries_label_description_and_step_number(self):
        wizards = wizard_engine.list_wizards_for_audience("tenant_admin")
        groups = wizard_categories.group_wizards_by_category(wizards)
        self.assertTrue(groups)
        # Step numbers are a 1-based consecutive progression in display order.
        self.assertEqual([g["step"] for g in groups], list(range(1, len(groups) + 1)))
        for g in groups:
            self.assertTrue(g["label"])
            self.assertTrue(g["description"])
            self.assertIn(g["key"], wizard_categories.CATEGORY_ORDER)

    def test_known_wizards_land_in_expected_stage(self):
        self.assertEqual(wizard_categories.category_for("mfa_setup"), "get_started")
        self.assertEqual(wizard_categories.category_for("teacher_gradebook_setup"), "configure")
        self.assertEqual(wizard_categories.category_for("alumni_engagement_pipeline"), "operate")
        self.assertEqual(
            wizard_categories.category_for("dynamic_safeguarding_incident_medical"), "govern"
        )

    def test_default_stage_is_configure(self):
        self.assertEqual(wizard_categories.DEFAULT_CATEGORY, "configure")


class DualWizardRbacDropTests(SimpleTestCase):
    """The 2 platform/infra wizards dropped from tenant audience (decision #2)."""

    def setUp(self):
        wizard_engine.load_wizard_registry()

    def test_dropped_wizards_are_now_operator_only(self):
        for key in ("cross_platform_whitelabel_branding", "legacy_data_extraction_pipeline"):
            wizard = wizard_engine.WIZARD_REGISTRY[key]
            self.assertEqual(tuple(wizard.audience), ("operator",), key)

    def test_dropped_wizards_absent_from_tenant_admin_index(self):
        tenant_keys = {
            w.wizard_key for w in wizard_engine.list_wizards_for_audience("tenant_admin")
        }
        self.assertNotIn("cross_platform_whitelabel_branding", tenant_keys)
        self.assertNotIn("legacy_data_extraction_pipeline", tenant_keys)

    def test_genuine_tenant_wizards_still_present(self):
        tenant_keys = {
            w.wizard_key for w in wizard_engine.list_wizards_for_audience("tenant_admin")
        }
        # account_migration stays tenant self-service (go-live import).
        self.assertIn("account_migration", tenant_keys)
        self.assertIn("custom_domain_setup", tenant_keys)


class WizardStatusMapTests(SimpleTestCase):
    """Pure derivation of per-wizard status from a SetupProgress namespace."""

    def test_completed_at_is_done(self):
        from apps.setup_studio.wizard_extras import wizard_status_map

        ns = {"mfa_setup": {"completed_at": "2026-06-16T00:00:00Z"}}
        self.assertEqual(wizard_status_map(ns), {"mfa_setup": "done"})

    def test_current_step_or_completed_steps_is_in_progress(self):
        from apps.setup_studio.wizard_extras import wizard_status_map

        ns = {
            "a": {"current_step_key": "step2"},
            "b": {"completed": ["step1"]},
        }
        self.assertEqual(
            wizard_status_map(ns), {"a": "in_progress", "b": "in_progress"}
        )

    def test_untouched_wizard_is_absent_from_map(self):
        from apps.setup_studio.wizard_extras import wizard_status_map

        ns = {"a": {"completed": []}}  # started nothing
        self.assertEqual(wizard_status_map(ns), {})

    def test_malformed_input_yields_empty_map(self):
        from apps.setup_studio.wizard_extras import wizard_status_map

        self.assertEqual(wizard_status_map(None), {})
        self.assertEqual(wizard_status_map("nope"), {})
        self.assertEqual(wizard_status_map({"x": "not-a-dict"}), {})


class StatusMapTenantScopeTests(SimpleTestCase):
    """SetupProgress is a SHARED-schema model — isolation rests entirely on the
    ``.filter(school=...)`` predicate. Lock it so a refactor can't drop the scope.
    """

    def test_status_map_filters_setupprogress_by_resolved_school(self):
        from types import SimpleNamespace
        from unittest import mock

        from apps.setup_studio import wizard_views

        school = SimpleNamespace(pk=42)
        captured: dict = {}

        class _QS:
            def filter(self, **kwargs):
                captured.update(kwargs)
                return self

            def first(self):
                return SimpleNamespace(
                    step_state={"wizards": {"mfa_setup": {"completed_at": "2026-06-16T00:00:00Z"}}}
                )

        fake_model = SimpleNamespace(objects=_QS())
        with mock.patch.object(wizard_views, "_resolve_school", return_value=school), \
                mock.patch("apps.setup_studio.models.SetupProgress", fake_model):
            result = wizard_views._resolve_wizard_status_map(mock.Mock())

        # The query MUST be scoped to the resolved school — never unscoped.
        self.assertEqual(captured.get("school"), school)
        self.assertEqual(result, {"mfa_setup": "done"})

    def test_status_map_returns_empty_when_no_school_resolves(self):
        from unittest import mock

        from apps.setup_studio import wizard_views

        with mock.patch.object(wizard_views, "_resolve_school", return_value=None):
            self.assertEqual(wizard_views._resolve_wizard_status_map(mock.Mock()), {})


class DecorateStagesProgressTests(SimpleTestCase):
    """The view-layer stage decorator computes honest per-stage + overall progress."""

    def _stub(self, key):
        from types import SimpleNamespace

        return SimpleNamespace(wizard_key=key)

    def test_progress_math_and_overall_rollup(self):
        from apps.setup_studio.wizard_views import _decorate_stages

        groups = [
            {"key": "get_started", "label": "Get started", "description": "d", "step": 1,
             "wizards": [self._stub("a"), self._stub("b")]},
            {"key": "configure", "label": "Configure", "description": "d", "step": 2,
             "wizards": [self._stub("c")]},
        ]
        status_map = {"a": "done", "b": "in_progress"}
        stages, overall = _decorate_stages(groups, status_map)

        self.assertEqual(stages[0]["progress"], {"done": 1, "total": 2, "pct": 50, "remaining": 1})
        self.assertEqual(stages[1]["progress"], {"done": 0, "total": 1, "pct": 0, "remaining": 1})
        # Per-card status is attached, defaulting untouched wizards to not_started.
        self.assertEqual([c["status"] for c in stages[0]["cards"]], ["done", "in_progress"])
        self.assertEqual(stages[1]["cards"][0]["status"], "not_started")
        self.assertEqual(overall, {"done": 1, "total": 3, "pct": 33, "remaining": 2})

    def test_empty_groups_give_zeroed_overall(self):
        from apps.setup_studio.wizard_views import _decorate_stages

        stages, overall = _decorate_stages([], {})
        self.assertEqual(stages, [])
        self.assertEqual(overall, {"done": 0, "total": 0, "pct": 0, "remaining": 0})

    def test_description_deduped_when_it_humanizes_to_the_title(self):
        from types import SimpleNamespace

        from apps.setup_studio.wizard_views import _decorate_stages

        # Both tokens humanize to "Account Migration" -> the card would print its
        # name twice; the description must be dropped.
        wiz = SimpleNamespace(
            wizard_key="account_migration",
            label_token="wizards.account_migration.label",
            description_token="wizards.account_migration.description",
        )
        groups = [{"key": "get_started", "label": "x", "description": "d", "step": 1,
                   "wizards": [wiz]}]
        card = _decorate_stages(groups, {})[0][0]["cards"][0]
        self.assertEqual(card["title"], "Account Migration")
        self.assertEqual(card["desc"], "")

    def test_distinct_description_is_kept(self):
        from types import SimpleNamespace

        from apps.setup_studio.wizard_views import _decorate_stages

        wiz = SimpleNamespace(
            wizard_key="mfa_setup",
            label_token="Set up two-factor authentication",
            description_token="Add a second step at sign-in.",
        )
        groups = [{"key": "get_started", "label": "x", "description": "d", "step": 1,
                   "wizards": [wiz]}]
        card = _decorate_stages(groups, {})[0][0]["cards"][0]
        self.assertEqual(card["title"], "Set up two-factor authentication")
        self.assertEqual(card["desc"], "Add a second step at sign-in.")


class BespokeIndexSurfaceTests(SimpleTestCase):
    """The redesigned index ships the bespoke lifecycle grammar + its stylesheet."""

    def test_tenant_index_uses_lifecycle_stages_and_status_cards(self):
        tpl = (_TEMPLATES / "tenant_wizard_index.html").read_text(encoding="utf-8")
        self.assertIn("rmc-wz-stages", tpl)
        self.assertIn("rmc-wz-hero", tpl)
        self.assertIn('data-rmc-wz-status="{{ card.status }}"', tpl)
        self.assertIn("rmc-wizard-engine.css", tpl)
        # Inline progress is a plain CSS custom-property number (token-gate safe).
        self.assertIn("--rmc-wz-pct:{{ stage.progress.pct }}", tpl)

    def test_operator_index_also_adopts_the_bespoke_grammar(self):
        tpl = (_TEMPLATES / "operator_wizard_index.html").read_text(encoding="utf-8")
        self.assertIn("rmc-wz-stages", tpl)
        self.assertIn("rmc-wizard-engine.css", tpl)

    def test_engine_stylesheet_defines_the_namespace(self):
        css = (
            _REPO_ROOT / "static" / "css" / "rmc-wizard-engine.css"
        ).read_text(encoding="utf-8")
        for selector in (".rmc-wz-card", ".rmc-wz-stage", ".rmc-wz-hero", ".rmc-wz-ring"):
            self.assertIn(selector, css)

    def test_index_injects_css_into_a_real_portal_block(self):
        # portal_base.html exposes {% block extrastyle %} in <head>, NOT extra_head.
        # Injecting CSS into the phantom `extra_head` block silently drops every
        # wizard stylesheet — the "entirely unstyled wizard surface" regression.
        tpl = (_TEMPLATES / "tenant_wizard_index.html").read_text(encoding="utf-8")
        self.assertIn("{% block extrastyle %}", tpl)
        self.assertNotIn("{% block extra_head %}", tpl)

    def test_step_run_template_also_uses_the_real_css_block(self):
        tpl = (_TEMPLATES / "tenant_wizard.html").read_text(encoding="utf-8")
        self.assertIn("{% block extrastyle %}", tpl)
        self.assertNotIn("{% block extra_head %}", tpl)


class OffcanvasDoublingGuardTests(SimpleTestCase):
    def test_mobile_offcanvas_is_hidden_on_large_screens(self):
        portal_base = (
            _REPO_ROOT / "templates" / "portal_base.html"
        ).read_text(encoding="utf-8")
        # The offcanvas sidebar carries d-lg-none so it cannot render inline
        # under the desktop sidebar (the "doubled nav" artifact).
        self.assertIn(
            'class="offcanvas offcanvas-start d-lg-none"',
            portal_base,
        )
