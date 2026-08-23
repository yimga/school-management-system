"""``runtime.locale.language_code`` must be a LANGUAGE, never the tenant's country.

``_step3_registry_context`` was fixed to read ``School.country_code`` (it used to
read a non-existent ``School.country``, so every tenant resolved to None). The
same commit fixed ``build_tenant_runtime_for_tenant`` to populate
``TenantContext.country`` from ``country_code``. What it did NOT fix is the one
other consumer of that field:

    language_code=tenant_ctx.country or "en"

While ``country`` was permanently None this line was harmlessly "en". Now that a
real ISO country code flows through it, a Cameroonian tenant's job-mode runtime
reports ``language_code="CM"`` — and when the remaining upstream reads in
``apps/tenancy/middleware.py`` are corrected, every REQUEST runtime does too.

The school already stores its language in ``School.default_language``; that is
what this context must carry.
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import TestCase

from apps.platform_runtime.runtime_resolver import (
    build_tenant_runtime,
    build_tenant_runtime_for_tenant,
)
from apps.schools.models import School
from apps.tenancy.context import TenantContext


def _ctx(school, *, country: str | None) -> TenantContext:
    return TenantContext(
        tenant_id=str(school.pk),
        schema_name=None,
        school_id=school.pk,
        country=country,
        timezone=None,
        feature_flags={},
        policy_overrides={},
        host="",
    )


class RuntimeLocaleLanguageTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Locale Language School",
            slug="locale-language-school",
            subdomain="locale-language-school",
            country_code="CM",
            default_language="fr",
        )

    def test_language_code_is_the_schools_language_not_its_country(self):
        runtime = build_tenant_runtime(
            _ctx(self.school, country="CM"), request=None, school=self.school
        )
        # Vacuity guard: the build must actually have resolved THIS tenant, or a
        # wrong language_code would be measured on an empty runtime.
        self.assertIsNotNone(runtime.locale)
        self.assertEqual(runtime.tenant.id, self.school.pk)
        self.assertEqual(runtime.locale.language_code, "fr")

    def test_country_code_never_leaks_into_language_code(self):
        """A school with no configured language must fall back to a LANGUAGE."""
        blank = School.objects.create(
            name="No Language School",
            slug="no-language-school",
            subdomain="no-language-school",
            country_code="DE",
            default_language="",
        )
        runtime = build_tenant_runtime(
            _ctx(blank, country="DE"), request=None, school=blank
        )
        self.assertIsNotNone(runtime.locale)
        self.assertEqual(runtime.tenant.id, blank.pk)
        self.assertNotEqual(runtime.locale.language_code, "DE")
        self.assertEqual(runtime.locale.language_code.split("-")[0], "en")

    def test_job_mode_runtime_reports_a_language(self):
        """The Celery/worker path is where the regression actually landed."""
        tenant = SimpleNamespace(
            id=self.school.pk, schema_name=None, school=self.school
        )
        runtime = build_tenant_runtime_for_tenant(tenant)
        self.assertIsNotNone(runtime.locale)
        self.assertEqual(runtime.tenant.id, self.school.pk)
        self.assertEqual(runtime.locale.language_code, "fr")
