"""Increment (l) — admission templates broadened to every region.

Increment (f) shipped ~13 curated countries; this widens the country_defaults
admission layer to the full regional footprint via convention groups (Anglophone/
Commonwealth = slash, Francophone/Lusophone/Hispanophone = dash, UK/Nordic/East
Asia = compact, US-style = bare sequence). These tests pin the regional
conventions, that every existing mapping is preserved, and that alpha-3 input
resolves the same as alpha-2.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.policies.country_admission_templates import (
    _COMPACT,
    _DASH,
    _SEQ_YEAR,
    _SLASH,
    GENERIC_ADMISSION_TEMPLATE,
    template_for_country,
)


class RegionalConventionTests(SimpleTestCase):
    def test_slash_for_anglophone_commonwealth(self):
        for iso in ("NG", "GH", "KE", "ZA", "RW", "ZW", "ZM", "SL", "GM",
                    "IN", "PK", "BD", "LK", "SG", "MY", "AE", "QA", "SA", "JM"):
            self.assertEqual(template_for_country(iso), _SLASH, iso)

    def test_dash_for_francophone_lusophone_hispanophone(self):
        for iso in ("FR", "CI", "SN", "ML", "BF", "TG", "GA", "CD", "MG",
                    "AO", "MZ", "ES", "PT", "IT", "BE", "MX", "BR", "AR", "CL", "CO"):
            self.assertEqual(template_for_country(iso), _DASH, iso)

    def test_compact_for_uk_nordic_east_asia(self):
        for iso in ("GB", "SE", "NO", "DK", "FI", "RU", "JP", "KR", "CN",
                    "ID", "TH", "VN", "EG", "MA", "DZ"):
            self.assertEqual(template_for_country(iso), _COMPACT, iso)

    def test_seq_year_for_us_style(self):
        for iso in ("US", "CA", "PH"):
            self.assertEqual(template_for_country(iso), _SEQ_YEAR, iso)


class BackwardCompatAndNormalizationTests(SimpleTestCase):
    def test_existing_mappings_preserved(self):
        # The 13 originally-curated countries must not change form.
        self.assertEqual(template_for_country("CM"), _SLASH)
        self.assertEqual(template_for_country("CMR"), _SLASH)
        self.assertEqual(template_for_country("US"), _SEQ_YEAR)
        self.assertEqual(template_for_country("USA"), _SEQ_YEAR)
        self.assertEqual(template_for_country("GB"), _COMPACT)
        self.assertEqual(template_for_country("FR"), _DASH)
        self.assertEqual(template_for_country("DE"), _DASH)

    def test_alpha3_matches_alpha2(self):
        for a2, a3 in (("NG", "NGA"), ("BR", "BRA"), ("SN", "SEN"),
                       ("JP", "JPN"), ("ZA", "ZAF"), ("SG", "SGP")):
            self.assertEqual(
                template_for_country(a3), template_for_country(a2), f"{a2}/{a3}"
            )

    def test_unknown_and_blank_are_generic(self):
        self.assertEqual(template_for_country("XX"), GENERIC_ADMISSION_TEMPLATE)
        self.assertEqual(template_for_country(""), GENERIC_ADMISSION_TEMPLATE)
