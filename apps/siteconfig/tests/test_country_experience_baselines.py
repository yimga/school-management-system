from django.test import SimpleTestCase

from apps.siteconfig.country_experience_baselines import (
    assert_country_baseline_invariants,
    baseline_index,
    list_country_experience_baselines,
)


class CountryExperienceBaselineTests(SimpleTestCase):
    def test_baselines_cover_200_plus_country_native_payment_postures(self):
        assert_country_baseline_invariants(min_count=200)
        rows = list_country_experience_baselines()
        self.assertGreaterEqual(len(rows), 200)

    def test_anchor_markets_have_currency_and_rail_context(self):
        index = baseline_index()
        for code in ("CM", "NG", "GH", "KE", "IN", "BR", "AE", "FR", "CA", "US"):
            with self.subTest(code=code):
                row = index[code]
                self.assertEqual(row.country_code, code)
                self.assertEqual(len(row.currency), 3)
                self.assertTrue(row.primary_rail)
                self.assertTrue(row.backup_rail)
                self.assertEqual(row.template_depth, "baseline_country_native")
