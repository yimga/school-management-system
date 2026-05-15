"""Wave A — G1: full lexicon cascade tests.

Complements `test_terminology_engine.py` (which already covers the legacy
4-key surface). These tests exercise the new layers:

* Country overlay via ``RuntimeDefaults.payload["lexicon.country_overrides"]``
* District / ancestor walk via ``School.parent_school``
* Plural resolution + auto-derivation
* Generic ``{% term %}`` templatetag (singular/plural/capitalize)
* ``lexicon_payload`` JSON-meta serialisation
"""

from __future__ import annotations

import json
import uuid

from django.template import Context, Engine
from django.test import RequestFactory, TestCase, override_settings

from apps.platform_runtime.models import RuntimeDefaults
from apps.schools.models import School
from apps.siteconfig.curriculum_templates_service import (
    reload_curriculum_templates_cache,
)
from apps.siteconfig.lexicon_catalog import (
    LEXICON_REGISTRY,
    auto_plural,
    default_plural,
    default_singular,
    grouped_by_category,
    is_known_key,
    lexicon_keys,
    normalise_override,
)
from apps.siteconfig.models import Plan
from apps.siteconfig.models_platform_catalog import RegionConfig
from apps.siteconfig.terminology_service import (
    lexicon_payload,
    resolve_all_terms,
    resolve_term,
)

_T_HOST = "lexicon.runmycampus.com"


def _make_school(*, slug_prefix="lex", country_code="", parent=None, plan=None, region=None, **settings_kw):
    slug = f"{slug_prefix}-{uuid.uuid4().hex[:8]}"
    school = School.objects.create(
        name=f"Lexicon School {slug}",
        slug=slug,
        subdomain=slug,
        is_active=True,
        plan=plan,
        default_region=region,
        country_code=country_code,
        parent_school=parent,
        settings={},
    )
    if settings_kw:
        base = dict(school.settings or {})
        base.update(settings_kw)
        school.settings = base
        school.save(update_fields=["settings"])
    return school


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class LexiconCatalogTests(TestCase):
    """Pure-Python helpers, no DB required."""

    def test_registry_has_known_canonical_keys(self):
        keys = set(lexicon_keys())
        # Spot-check a few high-traffic terms — the registry must contain these.
        for required in ("student", "teacher", "class", "term", "grade", "school"):
            self.assertIn(required, keys, msg=f"missing canonical key: {required}")

    def test_every_entry_has_four_fields(self):
        for key, entry in LEXICON_REGISTRY.items():
            self.assertEqual(len(entry), 4, msg=f"{key} entry malformed")
            sing, plur, cat, desc = entry
            self.assertTrue(sing, msg=f"{key} blank singular")
            self.assertTrue(plur, msg=f"{key} blank plural")
            self.assertTrue(cat, msg=f"{key} blank category")
            self.assertIsInstance(desc, str)

    def test_grouped_by_category_round_trips(self):
        groups = grouped_by_category()
        flat = [k for cat_keys in groups.values() for k in cat_keys]
        self.assertEqual(set(flat), set(lexicon_keys()))

    def test_is_known_key(self):
        self.assertTrue(is_known_key("student"))
        self.assertFalse(is_known_key("nonexistent_term_xyz"))

    def test_default_helpers(self):
        self.assertEqual(default_singular("student"), "Student")
        self.assertEqual(default_plural("student"), "Students")
        # Unknown key: singular returns itself; plural auto-derives.
        self.assertEqual(default_singular("unknown_key_zzz"), "unknown_key_zzz")
        self.assertTrue(default_plural("unknown_key_zzz"))

    def test_auto_plural_rules(self):
        self.assertEqual(auto_plural("Cat"), "Cats")
        self.assertEqual(auto_plural("City"), "Cities")
        self.assertEqual(auto_plural("Boy"), "Boys")  # vowel-y stays + s
        self.assertEqual(auto_plural("Class"), "Class")  # already ends in s, unchanged

    def test_normalise_override_shapes(self):
        self.assertEqual(normalise_override("Scholar"), {"singular": "Scholar"})
        self.assertEqual(
            normalise_override({"singular": "Scholar", "plural": "Scholars"}),
            {"singular": "Scholar", "plural": "Scholars"},
        )
        self.assertEqual(normalise_override({"singular": "Scholar"}), {"singular": "Scholar"})
        self.assertEqual(normalise_override({"singular": "  "}), {})
        self.assertEqual(normalise_override(""), {})
        self.assertEqual(normalise_override(None), {})
        self.assertEqual(normalise_override(123), {})


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class LexiconCascadeTests(TestCase):
    """Multi-layer cascade: defaults → country → curriculum → district → school."""

    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="Lex", slug="lex-plan", included_features=["core"], is_active=True
        )
        cls.region = RegionConfig.objects.create(
            code="LX", name="Lexland", timezone="UTC", default_currency="USD"
        )

    def setUp(self):
        reload_curriculum_templates_cache()
        # Reset RuntimeDefaults so country overlay state is hermetic per-test.
        RuntimeDefaults.objects.all().delete()

    # --- Layer 5: school override --------------------------------------

    def test_school_override_string_form(self):
        school = _make_school(plan=self.plan, region=self.region, terminology={"student": "Scholar"})
        self.assertEqual(resolve_term(school, "student"), "Scholar")
        # Plural auto-derives from override singular when no plural given.
        self.assertEqual(resolve_term(school, "student", plural=True), "Scholars")

    def test_school_override_dict_form_with_plural(self):
        school = _make_school(
            plan=self.plan,
            region=self.region,
            terminology={"class": {"singular": "Cohort", "plural": "Cohorts"}},
        )
        self.assertEqual(resolve_term(school, "class"), "Cohort")
        self.assertEqual(resolve_term(school, "class", plural=True), "Cohorts")

    # --- Layer 4: ancestor (district/group) walk -----------------------

    def test_ancestor_terminology_inherits_to_child(self):
        district = _make_school(
            slug_prefix="district",
            plan=self.plan,
            region=self.region,
            terminology={"teacher": "Sensei"},
        )
        child = _make_school(slug_prefix="child", plan=self.plan, region=self.region, parent=district)
        self.assertEqual(resolve_term(child, "teacher"), "Sensei")

    def test_school_override_beats_ancestor(self):
        district = _make_school(
            slug_prefix="district",
            plan=self.plan,
            region=self.region,
            terminology={"teacher": "Sensei"},
        )
        child = _make_school(
            slug_prefix="child",
            plan=self.plan,
            region=self.region,
            parent=district,
            terminology={"teacher": "Guide"},
        )
        self.assertEqual(resolve_term(child, "teacher"), "Guide")

    # --- Layer 2: country overlay --------------------------------------

    def test_country_overlay_applies_when_no_school_override(self):
        RuntimeDefaults.objects.create(
            payload={
                "lexicon.country_overrides": {
                    "FR": {"student": {"singular": "Élève", "plural": "Élèves"}}
                }
            }
        )
        school = _make_school(plan=self.plan, region=self.region, country_code="FR")
        self.assertEqual(resolve_term(school, "student"), "Élève")
        self.assertEqual(resolve_term(school, "student", plural=True), "Élèves")

    def test_school_override_beats_country_overlay(self):
        RuntimeDefaults.objects.create(
            payload={
                "lexicon.country_overrides": {
                    "FR": {"student": {"singular": "Élève", "plural": "Élèves"}}
                }
            }
        )
        school = _make_school(
            plan=self.plan,
            region=self.region,
            country_code="FR",
            terminology={"student": "Scholar"},
        )
        self.assertEqual(resolve_term(school, "student"), "Scholar")

    # --- Layer 3: curriculum template (legacy 4-key) -------------------

    def test_curriculum_template_terminology_applies_via_resolve_term(self):
        # american_k12 sets term="Semester"; verify the generic resolver picks it up.
        school = _make_school(
            plan=self.plan,
            region=self.region,
            curriculum_template_key="american_k12",
        )
        self.assertEqual(resolve_term(school, "term"), "Semester")

    def test_school_override_beats_curriculum_template(self):
        school = _make_school(
            plan=self.plan,
            region=self.region,
            curriculum_template_key="american_k12",
            terminology={"term": "Quarter"},
        )
        self.assertEqual(resolve_term(school, "term"), "Quarter")

    # --- Layer 1: defaults / unknown keys ------------------------------

    def test_unknown_key_falls_back_to_key_itself(self):
        school = _make_school(plan=self.plan, region=self.region)
        self.assertEqual(resolve_term(school, "no_such_term"), "no_such_term")

    def test_none_school_uses_registry_defaults(self):
        self.assertEqual(resolve_term(None, "student"), "Student")
        self.assertEqual(resolve_term(None, "student", plural=True), "Students")

    # --- resolve_all_terms / lexicon_payload ---------------------------

    def test_resolve_all_terms_returns_every_registry_key(self):
        school = _make_school(plan=self.plan, region=self.region, terminology={"student": "Scholar"})
        all_terms = resolve_all_terms(school)
        self.assertEqual(set(all_terms.keys()), set(LEXICON_REGISTRY.keys()))
        self.assertEqual(all_terms["student"]["singular"], "Scholar")
        # An unmodified key still resolves to its default.
        self.assertEqual(all_terms["teacher"]["singular"], "Teacher")

    def test_lexicon_payload_emits_only_overrides(self):
        school = _make_school(plan=self.plan, region=self.region, terminology={"student": "Scholar"})
        payload = lexicon_payload(school)
        self.assertIn("student", payload)
        # Default term must NOT appear in the compact payload.
        self.assertNotIn("teacher", payload)
        self.assertEqual(payload["student"]["s"], "Scholar")
        self.assertEqual(payload["student"]["p"], "Scholars")

    def test_lexicon_payload_is_empty_for_plain_tenant(self):
        school = _make_school(plan=self.plan, region=self.region)
        self.assertEqual(lexicon_payload(school), {})


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class LexiconTemplateTagTests(TestCase):
    """The generic ``{% term %}`` tag (and capitalize/plural variants)."""

    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="LexT", slug="lex-tag-plan", included_features=["core"], is_active=True
        )
        cls.region = RegionConfig.objects.create(
            code="LT", name="Tagland", timezone="UTC", default_currency="USD"
        )

    def setUp(self):
        reload_curriculum_templates_cache()

    def _engine(self):
        return Engine.get_default()

    def test_term_tag_resolves_singular_via_request_school(self):
        school = _make_school(
            plan=self.plan, region=self.region, terminology={"student": "Scholar"}
        )
        request = RequestFactory().get("/")
        request.school = school
        tpl = self._engine().from_string(
            "{% load terminology_tags %}{% term 'student' %}|{% term 'student' plural=True %}"
        )
        self.assertEqual(tpl.render(Context({"request": request})), "Scholar|Scholars")

    def test_term_tag_capitalize_option(self):
        request = RequestFactory().get("/")
        request.school = None  # defaults
        tpl = self._engine().from_string(
            "{% load terminology_tags %}{% term 'student' capitalize=True %}"
        )
        self.assertEqual(tpl.render(Context({"request": request})), "Student")

    def test_term_lower_tag(self):
        school = _make_school(
            plan=self.plan, region=self.region, terminology={"teacher": "Sensei"}
        )
        request = RequestFactory().get("/")
        request.school = school
        tpl = self._engine().from_string(
            "{% load terminology_tags %}{% term_lower 'teacher' %}"
        )
        self.assertEqual(tpl.render(Context({"request": request})), "sensei")

    def test_term_tag_fallback_when_no_school(self):
        tpl = self._engine().from_string("{% load terminology_tags %}{% term 'class' plural=True %}")
        self.assertEqual(tpl.render(Context({})), "Classes")


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class LexiconContextProcessorTests(TestCase):
    """The context processor emits a JSON meta payload usable by rmc-lexicon.js."""

    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="LexCP", slug="lex-cp-plan", included_features=["core"], is_active=True
        )
        cls.region = RegionConfig.objects.create(
            code="CP", name="CPland", timezone="UTC", default_currency="USD"
        )

    def test_context_processor_emits_valid_json_for_overridden_tenant(self):
        from apps.siteconfig.context_processors import lexicon_context

        school = _make_school(
            plan=self.plan, region=self.region, terminology={"student": "Scholar"}
        )
        request = RequestFactory().get("/")
        request.school = school
        ctx = lexicon_context(request)
        self.assertIn("rmc_lexicon_meta", ctx)
        self.assertIn("lexicon", ctx)
        payload = json.loads(ctx["rmc_lexicon_meta"])
        self.assertIn("student", payload)
        self.assertEqual(payload["student"]["s"], "Scholar")

    def test_context_processor_emits_empty_for_anonymous(self):
        from apps.siteconfig.context_processors import lexicon_context

        request = RequestFactory().get("/")
        # No request.school attribute set → anonymous / marketing visit.
        ctx = lexicon_context(request)
        self.assertEqual(ctx["rmc_lexicon_meta"], "")
        # `lexicon` dict still resolves to defaults for templates that need it.
        self.assertIn("student", ctx["lexicon"])
        self.assertEqual(ctx["lexicon"]["student"]["singular"], "Student")
