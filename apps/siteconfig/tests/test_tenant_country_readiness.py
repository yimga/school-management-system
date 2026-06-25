"""Country readiness context for 250-country scoring."""

from __future__ import annotations

from django.test import RequestFactory, SimpleTestCase

from apps.siteconfig.tenant_country_readiness import (
    country_readiness_context,
    resolve_effective_country_bonus,
)


class TenantCountryReadinessTests(SimpleTestCase):
    def test_matrix_country_without_payment_catalog_still_configured(self):
        request = RequestFactory().get("/")
        request.school = type(
            "School",
            (),
            {"country_code": "AD", "name": "Test"},
        )()
        request.site_settings = None
        request.SITE = None
        ctx = country_readiness_context(request)
        self.assertTrue(ctx["configured"])
        self.assertEqual(ctx["country_code"], "AD")
        self.assertGreater(ctx["auto_bonus"], 0)

    def test_auto_bonus_when_policy_explicit_zero(self):
        bonus = resolve_effective_country_bonus(
            {"experience_score_country_bonus": 0},
            country_ctx={"configured": True, "auto_bonus": 8},
        )
        self.assertEqual(bonus, 8)

    def test_explicit_bonus_overrides_auto(self):
        bonus = resolve_effective_country_bonus(
            {"experience_score_country_bonus": 12},
            country_ctx={"configured": True, "auto_bonus": 8},
        )
        self.assertEqual(bonus, 12)
