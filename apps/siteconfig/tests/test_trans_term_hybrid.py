"""Wave M: hybrid lexicon × i18n tag (`{% trans_term %}`) tests.

The hybrid tag resolves a canonical lexicon key:

* When a tenant override is in effect, return the override literally
  (locale-agnostic — tenant branding wins).
* When no override is in effect, fall through to gettext(source) for
  normal i18n.

This unlocks safe `{% trans %}` → `{% trans_term %}` conversion: tenant
overrides win when present; i18n catalog applies when absent.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from django.template import Context, Engine
from django.test import TestCase, override_settings
from django.utils.translation import override as translation_override

from apps.schools.models import School
from apps.siteconfig.models import Plan
from apps.siteconfig.models_platform_catalog import RegionConfig


def _make_school(plan, region, **settings_kw):
    slug = f"m1-{uuid.uuid4().hex[:8]}"
    return School.objects.create(
        name=slug, slug=slug, subdomain=slug, is_active=True,
        plan=plan, default_region=region, country_code="",
        settings=settings_kw.get("settings") or {},
    )


def _classroom_stub(terminology: dict | None = None):
    return SimpleNamespace(settings={"terminology": terminology} if terminology else {})


def _render(template_str: str, ctx: dict) -> str:
    engine = Engine(builtins=["apps.siteconfig.templatetags.terminology_tags"])
    return engine.from_string(template_str).render(Context(ctx))


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class TransTermHybridTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="M1", slug="m1-plan", included_features=["core"], is_active=True
        )
        cls.region = RegionConfig.objects.create(
            code="M1", name="M1land", timezone="UTC", default_currency="USD"
        )

    def test_no_override_falls_through_to_gettext_source(self):
        # English locale + no override + source="Student" → "Student".
        # (gettext returns the source string when no translation is loaded.)
        school = _make_school(self.plan, self.region)
        with translation_override("en"):
            out = _render(
                '{% trans_term "Student" key="student" %}',
                {"school": school},
            )
        self.assertEqual(out, "Student")

    def test_override_returns_literal_value(self):
        school = _make_school(
            self.plan, self.region,
            settings={"terminology": {"student": "Scholar"}},
        )
        with translation_override("en"):
            out = _render(
                '{% trans_term "Student" key="student" %}',
                {"school": school},
            )
        self.assertEqual(out, "Scholar")

    def test_override_wins_in_any_locale(self):
        """Tenant branding is locale-agnostic — override wins even when
        a French (etc.) locale is active.
        """
        school = _make_school(
            self.plan, self.region,
            settings={"terminology": {"student": "Scholar"}},
        )
        with translation_override("fr"):
            out = _render(
                '{% trans_term "Student" key="student" %}',
                {"school": school},
            )
        # The override is locale-agnostic.
        self.assertEqual(out, "Scholar")

    def test_no_override_plural_falls_through(self):
        school = _make_school(self.plan, self.region)
        with translation_override("en"):
            out = _render(
                '{% trans_term "Students" key="student" plural=True %}',
                {"school": school},
            )
        self.assertEqual(out, "Students")

    def test_override_plural_returns_lexicon_value(self):
        school = _make_school(
            self.plan, self.region,
            settings={"terminology": {"student": {"singular": "Scholar", "plural": "Scholars"}}},
        )
        with translation_override("en"):
            out = _render(
                '{% trans_term "Students" key="student" plural=True %}',
                {"school": school},
            )
        self.assertEqual(out, "Scholars")

    def test_classroom_override_wins(self):
        """K1's classroom layer takes precedence over school-level even
        through the hybrid tag.
        """
        school = _make_school(
            self.plan, self.region,
            settings={"terminology": {"student": "Scholar"}},
        )
        classroom = _classroom_stub({"student": "Cadet"})
        with translation_override("en"):
            out = _render(
                '{% trans_term "Student" key="student" classroom=classroom %}',
                {"school": school, "classroom": classroom},
            )
        self.assertEqual(out, "Cadet")

    def test_capitalize_applies_post_resolution(self):
        school = _make_school(
            self.plan, self.region,
            settings={"terminology": {"student": "scholar"}},  # lowercase override
        )
        with translation_override("en"):
            out = _render(
                '{% trans_term "Student" key="student" capitalize=True %}',
                {"school": school},
            )
        self.assertEqual(out, "Scholar")

    def test_school_kwarg_explicit_overrides_context(self):
        a = _make_school(
            self.plan, self.region,
            settings={"terminology": {"student": "Scholar"}},
        )
        b = _make_school(
            self.plan, self.region,
            settings={"terminology": {"student": "Cadet"}},
        )
        with translation_override("en"):
            out = _render(
                '{% trans_term "Student" key="student" school=b %}',
                {"school": a, "b": b},
            )
        self.assertEqual(out, "Cadet")

    def test_no_school_in_context_falls_through_to_gettext(self):
        with translation_override("en"):
            out = _render('{% trans_term "Student" key="student" %}', {})
        self.assertEqual(out, "Student")

    def test_distinct_keys_resolve_independently(self):
        school = _make_school(
            self.plan, self.region,
            settings={"terminology": {"student": "Scholar"}},
        )
        with translation_override("en"):
            out_student = _render(
                '{% trans_term "Student" key="student" %}',
                {"school": school},
            )
            out_teacher = _render(
                '{% trans_term "Teacher" key="teacher" %}',
                {"school": school},
            )
        self.assertEqual(out_student, "Scholar")
        # No override for teacher → falls through to gettext("Teacher").
        self.assertEqual(out_teacher, "Teacher")
