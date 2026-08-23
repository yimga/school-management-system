"""Registry context must resolve the tenant country from ``School.country_code``.

``_step3_registry_context`` read ``school.country`` — an attribute ``School`` does
not have (it has ``country_code``). Both halves of the expression were dead, so
``country_code`` was always None: the 5-minute cache key collapsed to
``...:registry_context:default`` for the whole fleet, the CountryRegistry lookup
never ran, and the currency fell through to ``CurrencyRegistry.objects.first()``
— whichever row sorts first under ``Meta.ordering = ['sort_order', 'name']``.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.core.cache import cache
from django.test import TestCase

from apps.platform_runtime.runtime_resolver import _step3_registry_context
from apps.registries.models import CountryRegistry, CurrencyRegistry
from apps.schools.models import School
from apps.tenancy.context import TenantContext


class RegistryContextCountryCodeTests(TestCase):
    def setUp(self):
        # Vacuity guard: if apps.registries is not installed the whole registry
        # block in _step3_registry_context is skipped and every assertion below
        # would pass/fail for the wrong reason.
        self.assertTrue(
            django_apps.is_installed("apps.registries"),
            "apps.registries must be installed or this test measures nothing",
        )
        # Sorts first under Meta.ordering = ['sort_order', 'name'], so it is what
        # the CurrencyRegistry.objects.first() fallback would hand back.
        CurrencyRegistry.objects.create(
            code="AED", name="AAA Dirham", symbol="d", sort_order=0
        )
        CurrencyRegistry.objects.create(
            code="XAF", name="Central African CFA Franc", symbol="FCFA", sort_order=50
        )
        CurrencyRegistry.objects.create(
            code="USD", name="US Dollar", symbol="$", sort_order=60
        )
        CountryRegistry.objects.create(
            code="CM", name="Cameroon", default_currency="XAF"
        )
        CountryRegistry.objects.create(
            code="US", name="United States", default_currency="USD"
        )
        self.cm_school = School.objects.create(
            name="Douala Academy",
            slug="douala-academy",
            subdomain="douala-academy",
            country_code="CM",
        )
        self.us_school = School.objects.create(
            name="Boston Academy",
            slug="boston-academy",
            subdomain="boston-academy",
            country_code="US",
        )
        self.ctx = TenantContext.empty()
        cache.clear()
        self.addCleanup(cache.clear)

    def test_country_comes_from_country_code(self):
        registry = _step3_registry_context(self.cm_school, self.ctx)
        self.assertIsNotNone(
            registry.country, "CountryRegistry lookup never ran — country_code was not read"
        )
        self.assertEqual(registry.country["code"], "CM")
        self.assertEqual(registry.currency["code"], "XAF")

    def test_cache_key_is_not_shared_across_countries(self):
        cm = _step3_registry_context(self.cm_school, self.ctx)
        us = _step3_registry_context(self.us_school, self.ctx)
        # Vacuity guard: the first call must itself be correct, otherwise a pair
        # of equally-wrong results could still differ by accident.
        self.assertEqual(cm.currency["code"], "XAF")
        self.assertEqual(
            us.currency["code"],
            "USD",
            "the US tenant was served the Cameroonian tenant's cached registry context",
        )
        self.assertEqual(us.country["code"], "US")

    def test_unknown_country_does_not_invent_a_currency(self):
        """A country with no registry row must fail visibly, not silently pick a row."""
        orphan = School.objects.create(
            name="Nowhere Academy",
            slug="nowhere-academy",
            subdomain="nowhere-academy",
            country_code="ZZ",
        )
        registry = _step3_registry_context(orphan, self.ctx)
        self.assertIsNone(registry.country)
        self.assertIsNone(
            registry.currency,
            "unknown country silently inherited CurrencyRegistry.objects.first()",
        )

    def test_tenant_context_country_still_wins_when_supplied(self):
        ctx = TenantContext(
            tenant_id="",
            schema_name=None,
            school_id=None,
            country="us",
            timezone=None,
            feature_flags={},
            policy_overrides={},
            host="",
        )
        registry = _step3_registry_context(self.cm_school, ctx)
        self.assertEqual(registry.country["code"], "US")
