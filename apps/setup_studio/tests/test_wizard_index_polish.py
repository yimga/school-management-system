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
