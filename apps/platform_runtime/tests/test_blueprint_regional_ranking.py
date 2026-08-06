"""Blueprints must be ranked by fit for the school's country/region.

Audit finding: ``list_blueprints`` was region-blind — a Cameroon school and a US
school saw the identical, unranked catalog even though each blueprint declares a
``region`` + ``regional_overlays``. ``rank_blueprints_for_school`` sorts the
region-matched blueprint first and annotates fit.
"""

from django.test import SimpleTestCase

from apps.platform_runtime.blueprint_contract import rank_blueprints_for_school


class _FakeSchool:
    def __init__(self, country_code="", default_region_id=None, school_type=""):
        self.country_code = country_code
        self.default_region_id = default_region_id
        self.school_type = school_type


class BlueprintRegionalRankingTests(SimpleTestCase):
    def test_cameroon_school_ranks_the_cm_blueprint_first(self):
        ranked = rank_blueprints_for_school(_FakeSchool(country_code="CM"))
        self.assertTrue(ranked)
        top = ranked[0]
        self.assertGreaterEqual(top["fit_score"], 40)
        self.assertEqual(str(top.get("region") or "").upper(), "CM")
        self.assertEqual(top["fit_label"], "Best match")

    def test_every_row_is_annotated_with_fit(self):
        ranked = rank_blueprints_for_school(_FakeSchool(country_code="CM"))
        for row in ranked:
            self.assertIn("fit_score", row)
            self.assertIn("fit_label", row)
            self.assertIsInstance(row["fit_reasons"], list)

    def test_cm_blueprint_does_not_top_a_us_school(self):
        ranked = rank_blueprints_for_school(_FakeSchool(country_code="US"))
        self.assertTrue(ranked)
        # A CM-specific blueprint must not be the default for a US school.
        self.assertNotEqual(str(ranked[0].get("region") or "").upper(), "CM")
        # US has no country==region match here, so nothing scores a "Best match".
        self.assertLess(ranked[0]["fit_score"], 40)
