"""The admin index rail must report the catalog's real totals.

Reported 2026-08-30 against the tenant admin index: the rail read
"CATALOG SECTIONS 5 / MODELS LISTED --" while the catalog held 6 sections and
277 models. Both numbers were wrong, for different reasons, and an em dash is
the rail's own "nothing here" rendering -- so the page read as empty rather
than as broken.

Every producer hands the rail the catalog MAPPING: ``{sections, entries,
model_count, section_count, app_count}``. A mapping iterates over its KEYS, so
the rail counted five "sections" -- the number of keys -- whatever the catalog
actually held. Underneath that, sections carry ``apps`` and a precomputed
``model_count`` but no ``models`` list, so the per-section reader scored every
section zero and the total collapsed to the em dash.

These exercise the module's private helpers on purpose: they are the whole of
the arithmetic, and driving them directly keeps the test off the database.
"""

from __future__ import annotations

import unittest

from apps.siteconfig.admin_page_aware_rail import (
    _catalog_totals,
    _section_model_count,
)

# The shape build_platform_admin_catalog really returns, trimmed to the fields
# the rail reads. Five keys, six sections: the two numbers the old reader
# confused for one another.
CATALOG = {
    "app_count": 27,
    "entries": [{"name": "Users"}] * 277,
    "model_count": 277,
    "section_count": 6,
    "sections": [
        {"title": "academic", "model_count": 32, "apps": [], "preview_models": []},
        {"title": "other", "model_count": 2, "apps": [], "preview_models": []},
        {"title": "people", "model_count": 17, "apps": [], "preview_models": []},
        {"title": "system", "model_count": 1, "apps": [], "preview_models": []},
        {"title": "config", "model_count": 200, "apps": [], "preview_models": []},
        {"title": "misc", "model_count": 25, "apps": [], "preview_models": []},
    ],
}


class CatalogTotalsTests(unittest.TestCase):
    def test_mapping_reports_its_sections_not_its_key_count(self) -> None:
        sections, _ = _catalog_totals(CATALOG)
        self.assertEqual(
            sections,
            6,
            "the rail counted the mapping's keys instead of its sections",
        )

    def test_mapping_reports_the_model_total(self) -> None:
        _, models = _catalog_totals(CATALOG)
        self.assertEqual(models, 277, "a zero total renders as an em dash")

    def test_the_fixture_can_actually_catch_the_key_count_bug(self) -> None:
        # Both assertions above compare numbers, so pin that this fixture
        # distinguishes them at all: 5 keys, 6 sections. A fixture where they
        # matched would pass against the broken reader.
        self.assertEqual(len(CATALOG), 5)
        self.assertEqual(len(CATALOG["sections"]), 6)
        self.assertNotEqual(len(CATALOG), len(CATALOG["sections"]))

    def test_sections_are_counted_without_the_mappings_own_total(self) -> None:
        # The second half of the defect: sections carry model_count, never a
        # models list. Drop the precomputed total so the per-section reader
        # has to do the work.
        catalog = {k: v for k, v in CATALOG.items() if k != "model_count"}
        _, models = _catalog_totals(catalog)
        self.assertEqual(models, 277)

    def test_a_bare_sequence_of_sections_still_works(self) -> None:
        # Back-compat: callers that already unwrapped must not regress.
        self.assertEqual(_catalog_totals(CATALOG["sections"]), (6, 277))

    def test_an_explicit_models_list_beats_the_precomputed_count(self) -> None:
        self.assertEqual(
            _section_model_count({"models": [1, 2, 3], "model_count": 99}), 3
        )

    def test_a_section_falls_back_to_its_apps(self) -> None:
        section = {"title": "x", "apps": [{"models": [1, 2]}, {"models": [3]}]}
        self.assertEqual(_section_model_count(section), 3)

    def test_empty_input_is_zero_rather_than_a_crash(self) -> None:
        self.assertEqual(_catalog_totals(None), (0, 0))
        self.assertEqual(_catalog_totals({}), (0, 0))
        self.assertEqual(_catalog_totals([]), (0, 0))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
