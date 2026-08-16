"""C1 closure — ``term_windows_by_count``: more than one term structure per country.

``config['term_windows']`` held a SINGLE structure, so a country whose schools run
different term counts (a 2-semester sector alongside a 3-trimester one) could only
represent one at a time; the other fell through to the even-split default. This was
the one documented deferral of the country-data closure. It is now shipped as an
optional, fully additive ``term_windows_by_count`` key at every cascade layer
(per-school ``settings``, per-profile ``config``, curated ``_TERM_CALENDARS_BY_COUNT``)
and through the catalog importer. This proves:

* the resolver prefers the by-count entry matching a school's requested term count,
  and falls back to the single ``term_windows`` when a count is absent;
* absent the key, behaviour is byte-for-byte the old behaviour (additive);
* ``term_windows_source`` reports the right layer when windows come via by-count;
* the catalog importer parses, validates (length must match count), merges, and
  makes both structures live on the shared profile — a school resolves each.
"""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase

from apps.academics.country_term_calendars import (
    _container_windows,
    _lookup_windows,
    term_windows_source,
)
from apps.academics.official_catalog import (
    OfficialCatalogError,
    _merge_into_config,
    import_catalog,
    parse_catalog,
)
from apps.schools.models import School

_W2 = [[9, 1, 1, 31], [2, 1, 6, 30]]                        # 2-term structure
_W3 = [[9, 1, 12, 15], [1, 8, 4, 10], [4, 25, 7, 25]]       # 3-term structure
_W2_T = [(9, 1, 1, 31), (2, 1, 6, 30)]                      # as the resolver returns it
_W3_T = [(9, 1, 12, 15), (1, 8, 4, 10), (4, 25, 7, 25)]


class ContainerWindowsHelperTests(SimpleTestCase):
    def test_prefers_by_count_then_falls_back_to_bare(self):
        container = {"term_windows": _W2, "term_windows_by_count": {"3": _W3}}
        self.assertEqual(_container_windows(container, 3), _W3)   # by-count entry
        self.assertEqual(_container_windows(container, 2), _W2)   # falls back to bare
        self.assertEqual(_container_windows(container, 4), _W2)   # absent count -> bare

    def test_tolerates_int_keys_and_missing(self):
        self.assertEqual(_container_windows({"term_windows_by_count": {3: _W3}}, 3), _W3)
        self.assertIsNone(_container_windows({}, 3))
        self.assertIsNone(_container_windows(None, 3))


class LookupByCountTests(SimpleTestCase):
    def test_per_school_by_count_selects_matching_structure(self):
        s = School(country_code="CM", settings={"term_windows_by_count": {"2": _W2, "3": _W3}})
        self.assertEqual(_lookup_windows(s, 2), _W2_T)
        self.assertEqual(_lookup_windows(s, 3), _W3_T)

    def test_bare_term_windows_unchanged_when_no_by_count(self):
        # Additive: without the new key, the single list matched by length is exactly
        # the old behaviour.
        s = School(country_code="CM", settings={"term_windows": _W3})
        self.assertEqual(_lookup_windows(s, 3), _W3_T)
        self.assertIsNone(_lookup_windows(s, 2))   # length mismatch -> None (even split)

    def test_source_reports_school_layer_for_by_count(self):
        s = School(country_code="CM", settings={"term_windows_by_count": {"2": _W2}})
        self.assertEqual(term_windows_source(s, 2), "school")


class ParseByCountTests(SimpleTestCase):
    def test_parse_accepts_and_normalizes(self):
        parsed = parse_catalog(
            {"country": "NG", "term_windows_by_count": {"2": _W2, "3": _W3}}
        )
        self.assertEqual(set(parsed["term_windows_by_count"]), {"2", "3"})
        self.assertEqual(parsed["term_windows_by_count"]["2"], _W2)

    def test_by_count_alone_satisfies_required_payload(self):
        parsed = parse_catalog({"country": "NG", "term_windows_by_count": {"3": _W3}})
        self.assertIn("term_windows_by_count", parsed)

    def test_rejects_length_mismatch(self):
        with self.assertRaises(OfficialCatalogError):
            parse_catalog({"country": "NG", "term_windows_by_count": {"3": _W2}})  # 2 under "3"

    def test_rejects_non_integer_count_key(self):
        with self.assertRaises(OfficialCatalogError):
            parse_catalog({"country": "NG", "term_windows_by_count": {"trimester": _W3}})

    def test_empty_payload_still_rejected(self):
        with self.assertRaises(OfficialCatalogError):
            parse_catalog({"country": "NG"})


class MergeByCountTests(SimpleTestCase):
    def test_merge_counts_changes_and_is_idempotent(self):
        parsed = parse_catalog({"country": "NG", "term_windows_by_count": {"2": _W2}})
        merged, changes = _merge_into_config({}, parsed)
        self.assertEqual(changes["term_windows_by_count"], 1)
        self.assertIn("2", merged["term_windows_by_count"])
        _again, changes2 = _merge_into_config(merged, parsed)
        self.assertEqual(changes2["term_windows_by_count"], 0)

    def test_merge_preserves_other_count_entries(self):
        base = parse_catalog({"country": "NG", "term_windows_by_count": {"2": _W2}})
        merged, _c = _merge_into_config({}, base)
        add3 = parse_catalog({"country": "NG", "term_windows_by_count": {"3": _W3}})
        merged2, changes = _merge_into_config(merged, add3)
        self.assertEqual(changes["term_windows_by_count"], 1)
        self.assertEqual(set(merged2["term_windows_by_count"]), {"2", "3"})   # 2 preserved


class ImportResolveByCountTests(TestCase):
    """DB — a two-structure import goes live on the shared profile; a school of that
    country resolves the matching structure for each term count, profile winning
    over the single curated calendar."""

    def _ng_school(self, subdomain):
        from apps.siteconfig.education_profile_engine import ensure_region_for_country

        region = ensure_region_for_country("NG")
        return School.objects.create(
            name="Lagos College", subdomain=subdomain, country_code="NG", default_region=region
        )

    def test_import_makes_both_structures_resolvable(self):
        # Distinct 3-term values so profile precedence over curated NG is unambiguous.
        prof_w3 = [[9, 5, 12, 20], [1, 10, 4, 12], [4, 28, 7, 28]]
        prof_w3_t = [(9, 5, 12, 20), (1, 10, 4, 12), (4, 28, 7, 28)]
        summary = import_catalog(
            parse_catalog(
                {
                    "country": "NG",
                    "term_windows_by_count": {"2": _W2, "3": prof_w3},
                    "source": "test-ministry",
                }
            )
        )
        self.assertEqual(summary["status"], "applied")
        self.assertEqual(summary["term_windows_by_count_changed"], 2)

        school = self._ng_school("ng-by-count")
        # 2-term: no curated NG 2-term exists — only the imported by-count makes it real.
        self.assertEqual(_lookup_windows(school, 2), _W2_T)
        # 3-term: the imported by-count wins over the single curated NG calendar.
        self.assertEqual(_lookup_windows(school, 3), prof_w3_t)
