"""Increment (p) — 100% sovereign-country coverage across all four catalogs.

The keystone (k) fixed the mechanism; (p) closes the DATA so NO sovereign country
falls back to the blunt generic. This test is the completeness contract: it walks
the authoritative ISO 3166-1 list (via pycountry) and asserts that EVERY sovereign
country (excluding uninhabited / non-self-governing territories where a national
school calendar is meaningless) resolves:

  * a well-formed academic-calendar shape (country_calendar_shape) — start month
    1..12, term count 1..12 — so its region seeds the right year window + term
    count and its curated term windows actually apply (the alignment guard passes);
  * a curated admission-number template (one of the four convention forms, never
    only the generic fallback);
  * a non-empty trade catalog for a vocational school.

If a future ISO country is added and left uncovered, this test fails — that is the
"nothing can be missed" ratchet.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.academics.country_term_calendars import country_calendar_shape
from apps.academics.country_trade_catalogs import resolve_trade_catalog
from apps.policies.country_admission_templates import (
    _COMPACT,
    _DASH,
    _SEQ_YEAR,
    _SLASH,
    template_for_country,
)
from apps.schools.models import School

# Non-applicable ISO entries: uninhabited islands, joint military/economic
# territories, and small non-self-governing dependencies that run their
# administering state's calendar rather than a distinct national one. A national
# academic calendar is not a meaningful default for these.
_EXEMPT = {
    "AQ", "BV", "GS", "HM", "TF", "UM",              # uninhabited / research-only
    "AX", "BL", "MF", "PM", "WF", "YT", "RE", "GP",  # FR/other overseas territories
    "MQ", "GF", "NC", "PF", "SJ",
    "IO", "PN", "SH", "FK", "GI", "VG", "AI", "MS",  # UK overseas territories
    "KY", "TC", "BM", "GG", "JE", "IM",
    "FO", "GL",                                       # DK autonomous (own systems, exempt)
    "CX", "CC", "NF",                                 # AU external territories
    "CK", "NU", "TK", "AS", "GU", "MP", "VI", "PR",   # NZ/US Pacific territories
    "AW", "CW", "SX", "BQ",                           # NL Caribbean
}


class SovereignCoverageContractTests(SimpleTestCase):
    def _iter_countries(self):
        try:
            import pycountry
        except Exception:  # pragma: no cover — dependency optional in some envs
            self.skipTest("pycountry not installed; cannot enumerate ISO countries")
        for c in pycountry.countries:
            code = c.alpha_2
            if code in _EXEMPT:
                continue
            yield code, getattr(c, "name", code)

    def test_every_sovereign_country_has_a_calendar_shape(self):
        missing = []
        malformed = []
        for code, name in self._iter_countries():
            shape = country_calendar_shape(code)
            if shape is None:
                missing.append(f"{code} ({name})")
                continue
            sm, tc = shape
            if not (1 <= sm <= 12 and 1 <= tc <= 12):
                malformed.append(f"{code}={shape}")
        self.assertEqual(missing, [], f"countries with no academic-calendar shape: {missing}")
        self.assertEqual(malformed, [], f"malformed shapes: {malformed}")

    def test_every_sovereign_country_has_a_curated_admission_template(self):
        known = {_SLASH, _DASH, _COMPACT, _SEQ_YEAR}
        missing = []
        for code, name in self._iter_countries():
            if template_for_country(code) not in known:
                missing.append(f"{code} ({name})")
        self.assertEqual(missing, [], f"countries without a curated admission template: {missing}")

    def test_every_country_yields_a_non_empty_trade_catalog(self):
        empty = []
        for code, name in self._iter_countries():
            cat = resolve_trade_catalog(School(country_code=code))
            if not cat or not any(trades for _, trades in cat):
                empty.append(f"{code} ({name})")
        self.assertEqual(empty, [], f"countries with an empty trade catalog: {empty}")


class RegionalShapeSpotChecks(SimpleTestCase):
    """Pin a representative country per newly-added region to its real shape."""

    def test_spot_shapes(self):
        cases = {
            # Europe
            "PL": (9, 2), "CZ": (9, 2), "IS": (8, 2), "MT": (9, 3), "LU": (9, 3),
            # Central Asia / MENA
            "KZ": (9, 2), "AF": (3, 2), "PS": (9, 2),
            # Asia
            "MM": (6, 2), "KH": (11, 2), "KP": (4, 2), "TW": (9, 2), "BT": (2, 2),
            # Latin America (southern Feb/Mar; northern Jan/Aug/Sep)
            "BO": (2, 2), "UY": (3, 2), "VE": (9, 3), "DO": (8, 2), "GT": (1, 2),
            "SR": (10, 2),
            # Caribbean (Commonwealth) & Pacific
            "BS": (9, 3), "FM": (8, 2), "TO": (1, 3), "VU": (2, 3),
        }
        for code, expected in cases.items():
            self.assertEqual(country_calendar_shape(code), expected, code)
