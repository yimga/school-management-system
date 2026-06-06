"""Signup migration vendor recommendations + calendar display enrichment."""

from django.test import RequestFactory, SimpleTestCase

from apps.siteconfig.country_localization_service import resolve_country_pack
from apps.siteconfig.signup_migration_recommendations import (
    migration_context_for_country,
    order_onboarding_vendors,
    recommended_migration_vendors,
    recommended_onboarding_vendor_slugs,
)
from apps.schools.onboarding_vendors import ONBOARDING_VENDORS
from apps.siteconfig.views_country_localization import country_localization_pack


class SignupMigrationRecommendationsTests(SimpleTestCase):
    databases = {"default"}

    def test_china_prioritizes_csv_and_international_platforms(self):
        rec = recommended_migration_vendors("CN")
        self.assertEqual(rec[0], "csv")
        self.assertIn("managebac", rec[:4])

    def test_us_prioritizes_district_sis_vendors(self):
        rec = recommended_migration_vendors("US")
        self.assertEqual(rec[0], "powerschool")

    def test_api_pack_includes_migration_context(self):
        request = RequestFactory().get("/api/v1/localization/CM/")
        data = __import__("json").loads(country_localization_pack(request, "CM").content)
        self.assertIn("migration", data)
        self.assertTrue(data["migration"]["recommended_vendors"])
        self.assertTrue(data["migration"]["hint"])

    def test_cn_calendar_sub_derived_from_term_names(self):
        pack = resolve_country_pack("CN")
        cal = pack["calendar_systems"][0]
        self.assertIn("第一学期", cal.get("sub", ""))
        self.assertIn("第二学期", cal.get("sub", ""))

    def test_cn_has_bilingual_language_picker(self):
        pack = resolve_country_pack("CN")
        langs = pack.get("languages") or []
        codes = {str(l.get("code") or "").lower() for l in langs}
        self.assertIn("zh-hans", codes)
        self.assertIn("en", codes)

    def test_migration_context_shape(self):
        ctx = migration_context_for_country("NG")
        self.assertEqual(ctx["country_code"], "NG")
        self.assertIsInstance(ctx["recommended_vendors"], list)
        self.assertTrue(ctx["hint"])

    def test_onboarding_vendor_order_maps_csv_to_spreadsheet(self):
        slugs = recommended_onboarding_vendor_slugs("CN")
        self.assertEqual(slugs[0], "spreadsheet")
        ordered = order_onboarding_vendors(ONBOARDING_VENDORS, "CN")
        self.assertEqual(ordered[0].slug, "spreadsheet")
