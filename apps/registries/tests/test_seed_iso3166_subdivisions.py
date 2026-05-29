"""Phase 3B — tests for ISO 3166-2 subdivision seed helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from apps.registries.services import (
    map_pycountry_subdivision_type,
    seed_iso3166_subdivisions,
    subdivision_code_from_iso3166,
)


class Iso3166SubdivisionHelperTests(SimpleTestCase):
    def test_subdivision_code_strips_country_prefix(self):
        self.assertEqual(subdivision_code_from_iso3166("US-CA", "US"), "CA")
        self.assertEqual(subdivision_code_from_iso3166("CA-ON", "CA"), "ON")

    def test_map_pycountry_subdivision_type_normalizes_labels(self):
        self.assertEqual(map_pycountry_subdivision_type("State"), "state")
        self.assertEqual(
            map_pycountry_subdivision_type("Administrative region"),
            "administrative_region",
        )
        self.assertEqual(map_pycountry_subdivision_type(None), "subdivision")


class SeedIso3166SubdivisionsTests(SimpleTestCase):
    @mock.patch("pycountry.subdivisions.get")
    @mock.patch("apps.registries.services.SubdivisionRegistry.objects.update_or_create")
    @mock.patch("apps.registries.services.ensure_country_registry_seed")
    @mock.patch("apps.registries.services.CountryRegistry.objects")
    @mock.patch("apps.registries.services._sovereign_country_codes_from_matrix")
    def test_seed_fixture_country_uses_update_or_create(
        self,
        mock_sovereign,
        mock_country_objects,
        mock_ensure_seed,
        mock_update_or_create,
        mock_subdivisions_get,
    ):
        mock_sovereign.return_value = frozenset({"US"})
        country = SimpleNamespace(code="US", name="United States")
        filtered_qs = mock.Mock()
        filtered_qs.order_by.return_value = [country]
        filtered_qs.count.return_value = 1
        mock_country_objects.all.return_value.filter.return_value = filtered_qs
        mock_subdivisions_get.return_value = [
            SimpleNamespace(code="US-CA", name="California", type="State"),
        ]
        mock_update_or_create.return_value = (mock.Mock(), True)

        result = seed_iso3166_subdivisions(country_codes=["US"])

        mock_update_or_create.assert_called_once()
        kwargs = mock_update_or_create.call_args.kwargs
        self.assertEqual(kwargs["country"], country)
        self.assertEqual(kwargs["code"], "CA")
        self.assertEqual(kwargs["defaults"]["subdivision_type"], "state")
        self.assertTrue(kwargs["defaults"]["metadata"]["iso3166_2"])
        self.assertEqual(result.subdivisions_created, 1)
        self.assertEqual(result.countries_with_subdivisions, ("US",))

    @mock.patch("pycountry.subdivisions.get")
    @mock.patch("apps.registries.services.SubdivisionRegistry.objects.update_or_create")
    @mock.patch("apps.registries.services.ensure_country_registry_seed")
    @mock.patch("apps.registries.services.CountryRegistry.objects")
    @mock.patch("apps.registries.services._sovereign_country_codes_from_matrix")
    def test_sovereign_without_pycountry_gets_national_fallback(
        self,
        mock_sovereign,
        mock_country_objects,
        mock_ensure_seed,
        mock_update_or_create,
        mock_subdivisions_get,
    ):
        mock_sovereign.return_value = frozenset({"VA"})
        country = SimpleNamespace(code="VA", name="Holy See (Vatican City State)")
        filtered_qs = mock.Mock()
        filtered_qs.order_by.return_value = [country]
        filtered_qs.count.return_value = 1
        mock_country_objects.all.return_value.filter.return_value = filtered_qs
        mock_subdivisions_get.return_value = []
        mock_update_or_create.return_value = (mock.Mock(), True)

        result = seed_iso3166_subdivisions(country_codes=["VA"])

        mock_update_or_create.assert_called_once()
        kwargs = mock_update_or_create.call_args.kwargs
        self.assertEqual(kwargs["code"], "NAT")
        self.assertEqual(kwargs["defaults"]["subdivision_type"], "country")
        self.assertEqual(kwargs["defaults"]["metadata"]["source"], "national_fallback")
        self.assertEqual(result.countries_with_subdivisions, ("VA",))
