"""Wave K1: classroom-level lexicon override tests.

The classroom layer is the most-specific cascade tier — overrides
applied to ``Classroom.settings["terminology"]`` take precedence over
school-level overrides, ancestor overrides, country overlay, and the
registry default.

A classroom-less call must behave identically to pre-K1 (no regression).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from django.template import Context, Engine
from django.test import TestCase, override_settings

from apps.schools.models import School
from apps.siteconfig.models import Plan
from apps.siteconfig.models_platform_catalog import RegionConfig
from apps.siteconfig.terminology_service import (
    lexicon_payload,
    resolve_all_terms,
    resolve_term,
)


def _make_school(plan, region, **kw):
    slug = f"k1-{uuid.uuid4().hex[:8]}"
    return School.objects.create(
        name=slug, slug=slug, subdomain=slug, is_active=True,
        plan=plan, default_region=region, country_code="", settings=kw.get("settings") or {},
    )


def _classroom_stub(terminology: dict | None = None):
    """Lightweight Classroom-shaped stub: the resolver only reads ``.settings``."""
    return SimpleNamespace(settings={"terminology": terminology} if terminology else {})


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class ClassroomLexiconLayerTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="K1", slug="k1-plan", included_features=["core"], is_active=True
        )
        cls.region = RegionConfig.objects.create(
            code="K1", name="K1land", timezone="UTC", default_currency="USD"
        )

    def test_classroom_layer_overrides_school_layer(self):
        school = _make_school(
            self.plan, self.region,
            settings={"terminology": {"student": "Scholar"}},
        )
        classroom = _classroom_stub({"student": "Cadet"})
        self.assertEqual(resolve_term(school, "student"), "Scholar")
        self.assertEqual(
            resolve_term(school, "student", classroom=classroom), "Cadet"
        )

    def test_classroom_layer_derives_plural_when_only_singular_set(self):
        school = _make_school(self.plan, self.region)
        classroom = _classroom_stub({"student": "Cadet"})
        self.assertEqual(
            resolve_term(school, "student", plural=True, classroom=classroom),
            "Cadets",
        )

    def test_classroom_layer_explicit_plural_wins(self):
        school = _make_school(self.plan, self.region)
        classroom = _classroom_stub(
            {"student": {"singular": "Cadet", "plural": "The Corps"}}
        )
        self.assertEqual(
            resolve_term(school, "student", plural=True, classroom=classroom),
            "The Corps",
        )

    def test_classroom_layer_independent_per_classroom(self):
        school = _make_school(self.plan, self.region)
        a = _classroom_stub({"student": "Scholar"})
        b = _classroom_stub({"student": "Cadet"})
        self.assertEqual(resolve_term(school, "student", classroom=a), "Scholar")
        self.assertEqual(resolve_term(school, "student", classroom=b), "Cadet")
        # School-level resolution still pristine
        self.assertEqual(resolve_term(school, "student"), "Student")

    def test_classroom_with_no_settings_field_does_not_crash(self):
        school = _make_school(
            self.plan, self.region,
            settings={"terminology": {"student": "Scholar"}},
        )
        classroom = SimpleNamespace()  # no `settings` attribute at all
        self.assertEqual(
            resolve_term(school, "student", classroom=classroom), "Scholar"
        )

    def test_classroom_with_non_dict_terminology_falls_back(self):
        school = _make_school(self.plan, self.region)
        classroom = SimpleNamespace(settings={"terminology": "not-a-dict"})
        self.assertEqual(resolve_term(school, "student", classroom=classroom), "Student")

    def test_resolve_all_terms_honours_classroom_layer(self):
        school = _make_school(
            self.plan, self.region,
            settings={"terminology": {"student": "Scholar"}},
        )
        classroom = _classroom_stub({"student": "Cadet", "class": "Cohort"})
        terms = resolve_all_terms(school, classroom=classroom)
        self.assertEqual(terms["student"]["singular"], "Cadet")
        self.assertEqual(terms["class"]["singular"], "Cohort")

    def test_lexicon_payload_emits_classroom_overrides(self):
        school = _make_school(self.plan, self.region)
        classroom = _classroom_stub({"student": "Cadet"})
        payload = lexicon_payload(school, classroom=classroom)
        self.assertIn("student", payload)
        self.assertEqual(payload["student"]["s"], "Cadet")
        self.assertEqual(payload["student"]["p"], "Cadets")

    def test_term_template_tag_accepts_classroom_kwarg(self):
        school = _make_school(self.plan, self.region)
        classroom = _classroom_stub({"student": "Cadet"})
        engine = Engine(builtins=["apps.siteconfig.templatetags.terminology_tags"])
        tmpl = engine.from_string(
            '{% term "student" classroom=classroom %} / '
            '{% term "student" plural=True classroom=classroom %}'
        )
        rendered = tmpl.render(Context({"school": school, "classroom": classroom}))
        self.assertEqual(rendered, "Cadet / Cadets")

    def test_term_template_tag_picks_classroom_from_context_var(self):
        school = _make_school(self.plan, self.region)
        classroom = _classroom_stub({"student": "Cadet"})
        engine = Engine(builtins=["apps.siteconfig.templatetags.terminology_tags"])
        tmpl = engine.from_string('{% term "student" %}')
        rendered = tmpl.render(Context({"school": school, "classroom": classroom}))
        self.assertEqual(rendered, "Cadet")
