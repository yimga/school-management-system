"""Unit tests for the pure declared-vs-actual seed catalog diff.

No database, no Django settings, no fixtures: the module under test imports only
the standard library, so every number here is reproducible by anyone with a
Python interpreter and the repo checked out. That is the point -- the claim this
reconciler exists to replace ("12 missing") could not be reproduced by anybody,
because the only evidence for it was a console line whose list was capped at
twelve entries.

Run standalone (no pytest, no test database):

    python -m unittest apps.siteconfig.tests.test_seed_catalog_reconciler -v
"""

from __future__ import annotations

import json
import unittest

from apps.siteconfig.seed_catalog_reconciler import (
    CatalogDiff,
    build_receipt,
    diff_catalog,
    manifest_checksum,
    normalize_codes,
)

# The real shape of the case this was built for: the institution-type manifest
# declares 21 codes, of which 9 predate the 2026-09-02 expansion.
FOUNDING_NINE = [
    "BASE_SCHOOL",
    "TECHNICAL_COLLEGE",
    "STEM_ACADEMY",
    "PRIMARY_SCHOOL",
    "SECONDARY_SCHOOL",
    "NURSERY_SCHOOL",
    "UNIVERSITY",
    "TRAINING_CENTER",
    "SPECIAL_SCHOOL",
]
ADDED_TWELVE = [
    "GYMNASIUM",
    "SIXTH_FORM_COLLEGE",
    "MADRASAH",
    "INTERMEDIATE_COLLEGE",
    "BACHILLERATO",
    "SECUNDARIA_TECNICA",
    "INSTITUTO_PROFESIONAL",
    "COMMUNITY_COLLEGE",
    "MAGNET_SCHOOL",
    "GRANDE_ECOLE",
    "POLYTECHNIC",
    "ADULT_EDUCATION_CENTER",
]
DECLARED_21 = FOUNDING_NINE + ADDED_TWELVE


class NormalizeCodesTests(unittest.TestCase):
    def test_sorts_deduplicates_and_trims(self):
        self.assertEqual(
            normalize_codes([" b ", "a", "b", "a"]),
            ("a", "b"),
        )

    def test_drops_empty_and_none(self):
        self.assertEqual(normalize_codes(["a", "", "   ", None]), ("a",))

    def test_is_case_sensitive(self):
        # Two rows to the database's unique index, so two entries here.
        self.assertEqual(normalize_codes(["A", "a"]), ("A", "a"))

    def test_coerces_non_strings(self):
        self.assertEqual(normalize_codes([1, "1", 2]), ("1", "2"))


class ManifestChecksumTests(unittest.TestCase):
    def test_is_order_independent(self):
        self.assertEqual(
            manifest_checksum(["a", "b", "c"]),
            manifest_checksum(["c", "a", "b"]),
        )

    def test_changes_when_a_code_is_added(self):
        self.assertNotEqual(manifest_checksum(DECLARED_21), manifest_checksum(FOUNDING_NINE))

    def test_changes_when_a_code_is_renamed(self):
        renamed = ["GYMNASIUM_RENAMED" if c == "GYMNASIUM" else c for c in DECLARED_21]
        self.assertNotEqual(manifest_checksum(DECLARED_21), manifest_checksum(renamed))

    def test_is_prefixed_and_hex(self):
        value = manifest_checksum(["a"])
        self.assertTrue(value.startswith("sha256:"))
        self.assertEqual(len(value), len("sha256:") + 64)


class DiffCatalogTests(unittest.TestCase):
    def test_reports_the_twelve_added_codes_as_missing(self):
        diff = diff_catalog(
            "registry.institution_types",
            declared=DECLARED_21,
            actual=FOUNDING_NINE,
        )
        self.assertEqual(diff.declared_count, 21)
        self.assertEqual(diff.present_count, 9)
        self.assertEqual(diff.missing_count, 12)
        self.assertEqual(sorted(diff.missing), sorted(ADDED_TWELVE))
        self.assertFalse(diff.in_sync)

    def test_tally_closes(self):
        """present + missing == declared. The receipt is worthless if its own
        arithmetic does not add up, and `present_count` is counted rather than
        derived, so this is a real assertion and not a tautology."""
        diff = diff_catalog("k", declared=DECLARED_21, actual=FOUNDING_NINE + ["EXTRA"])
        self.assertEqual(diff.present_count + diff.missing_count, diff.declared_count)

    def test_in_sync_when_everything_present(self):
        diff = diff_catalog("k", declared=DECLARED_21, actual=DECLARED_21)
        self.assertTrue(diff.in_sync)
        self.assertEqual(diff.missing, ())
        self.assertEqual(diff.present_count, 21)

    def test_extra_rows_do_not_break_in_sync(self):
        # A tenant-authored global role is legitimate; it is reported, not deleted.
        diff = diff_catalog("k", declared=["A"], actual=["A", "CUSTOM"])
        self.assertTrue(diff.in_sync)
        self.assertEqual(diff.extra, ("CUSTOM",))

    def test_inactive_is_intersected_with_declared(self):
        diff = diff_catalog(
            "k",
            declared=["A", "B"],
            actual=["A", "B", "GHOST"],
            inactive=["B", "GHOST"],
        )
        # GHOST is inactive but undeclared, so it is an extra, not our problem.
        self.assertEqual(diff.inactive, ("B",))
        self.assertEqual(diff.extra, ("GHOST",))

    def test_a_present_but_inactive_row_is_not_missing(self):
        """The distinction that keeps --apply from inserting a duplicate the
        unique index would refuse: the row EXISTS, it is merely switched off."""
        diff = diff_catalog("k", declared=["A"], actual=["A"], inactive=["A"])
        self.assertEqual(diff.missing, ())
        self.assertEqual(diff.inactive, ("A",))
        self.assertTrue(diff.in_sync)

    def test_whitespace_and_duplicates_do_not_create_phantom_drift(self):
        diff = diff_catalog("k", declared=["A", "A", " B "], actual=[" A", "B"])
        self.assertTrue(diff.in_sync)
        self.assertEqual(diff.declared_count, 2)

    def test_carries_metadata_through(self):
        diff = diff_catalog(
            "catalog.access_roles",
            declared=["A"],
            actual=[],
            model_label="accounts.AccessRole",
            natural_key="code",
            apply_supported=False,
            remedy="run migrate accounts",
        )
        self.assertEqual(diff.model_label, "accounts.AccessRole")
        self.assertFalse(diff.apply_supported)
        self.assertEqual(diff.remedy, "run migrate accounts")


class ReceiptTruncationTests(unittest.TestCase):
    """The regression seal for the defect that motivated this module.

    ``platform_seed_audit`` renders ``missing[:12]``, so a reader counting the
    printed codes reads twelve whatever the true figure is. These tests assert
    the receipt does not do that.
    """

    def test_missing_list_is_not_capped_at_twelve(self):
        declared = [f"CODE_{i:02d}" for i in range(30)]
        diff = diff_catalog("k", declared=declared, actual=[])
        payload = diff.to_dict()
        self.assertEqual(payload["missing_count"], 30)
        self.assertEqual(len(payload["missing"]), 30)

    def test_twelve_missing_is_distinguishable_from_fifty_missing(self):
        twelve = diff_catalog("k", declared=[f"C{i}" for i in range(12)], actual=[])
        fifty = diff_catalog("k", declared=[f"C{i}" for i in range(50)], actual=[])
        self.assertNotEqual(
            len(twelve.to_dict()["missing"]), len(fifty.to_dict()["missing"])
        )

    def test_extra_list_is_not_capped(self):
        diff = diff_catalog("k", declared=[], actual=[f"X{i}" for i in range(25)])
        self.assertEqual(len(diff.to_dict()["extra"]), 25)


class ReceiptTests(unittest.TestCase):
    def _receipt(self):
        return build_receipt(
            [
                diff_catalog(
                    "registry.institution_types",
                    declared=DECLARED_21,
                    actual=FOUNDING_NINE,
                ),
                diff_catalog(
                    "catalog.access_roles",
                    declared=["ADMIN", "TEACHER"],
                    actual=["ADMIN", "TEACHER", "CUSTOM"],
                    apply_supported=False,
                    remedy="run migrate accounts",
                ),
            ],
            scope="all",
            generated_at="2026-09-06T00:00:00+00:00",
        )

    def test_totals_close_across_catalogs(self):
        totals = self._receipt().totals
        self.assertEqual(totals["catalogs"], 2)
        self.assertEqual(totals["declared"], 23)
        self.assertEqual(totals["present"] + totals["missing"], totals["declared"])
        self.assertEqual(totals["missing"], 12)
        self.assertEqual(totals["extra"], 1)

    def test_drifted_lists_only_catalogs_with_missing_rows(self):
        receipt = self._receipt()
        self.assertEqual(
            [d.key for d in receipt.drifted], ["registry.institution_types"]
        )

    def test_has_drift_ignores_extras_by_default(self):
        receipt = build_receipt([diff_catalog("k", declared=["A"], actual=["A", "B"])])
        self.assertFalse(receipt.has_drift())
        self.assertTrue(receipt.has_drift(include_extra=True))

    def test_clean_receipt_has_no_drift(self):
        receipt = build_receipt([diff_catalog("k", declared=["A"], actual=["A"])])
        self.assertFalse(receipt.has_drift())
        self.assertFalse(receipt.has_drift(include_extra=True))
        self.assertTrue(receipt.to_dict()["in_sync"])

    def test_manifest_checksum_is_stable_and_content_sensitive(self):
        first = self._receipt().manifest_checksum
        self.assertEqual(first, self._receipt().manifest_checksum)
        changed = build_receipt(
            [
                diff_catalog(
                    "registry.institution_types",
                    declared=FOUNDING_NINE,  # a different declared manifest
                    actual=FOUNDING_NINE,
                ),
                diff_catalog(
                    "catalog.access_roles",
                    declared=["ADMIN", "TEACHER"],
                    actual=["ADMIN", "TEACHER", "CUSTOM"],
                ),
            ]
        )
        self.assertNotEqual(first, changed.manifest_checksum)

    def test_checksum_does_not_depend_on_actual_database_state(self):
        """It fingerprints the DECLARED manifest. Two boxes with different data
        but the same code must produce the same checksum, or the receipt cannot
        be used to compare them."""
        a = build_receipt([diff_catalog("k", declared=["A", "B"], actual=[])])
        b = build_receipt([diff_catalog("k", declared=["A", "B"], actual=["A", "B"])])
        self.assertEqual(a.manifest_checksum, b.manifest_checksum)

    def test_to_json_is_parseable_and_carries_the_full_lists(self):
        payload = json.loads(self._receipt().to_json())
        self.assertEqual(payload["receipt_version"], "1")
        self.assertEqual(payload["scope"], "all")
        self.assertEqual(payload["mode"], "read-only")
        self.assertFalse(payload["in_sync"])
        institution = next(
            c for c in payload["catalogs"] if c["key"] == "registry.institution_types"
        )
        self.assertEqual(len(institution["missing"]), 12)
        roles = next(
            c for c in payload["catalogs"] if c["key"] == "catalog.access_roles"
        )
        self.assertFalse(roles["apply_supported"])
        self.assertEqual(roles["remedy"], "run migrate accounts")

    def test_created_rows_are_recorded(self):
        receipt = build_receipt(
            [diff_catalog("k", declared=["A", "B"], actual=["A", "B"])],
            mode="applied",
            created=[("k", ["B"])],
        )
        self.assertEqual(receipt.created_count, 1)
        self.assertEqual(receipt.to_dict()["created"], {"k": ["B"]})
        self.assertEqual(receipt.to_dict()["mode"], "applied")

    def test_empty_receipt_is_in_sync_and_totals_zero(self):
        receipt = build_receipt([])
        self.assertFalse(receipt.has_drift())
        self.assertEqual(receipt.totals["declared"], 0)
        self.assertEqual(receipt.totals["catalogs"], 0)


class CatalogDiffShapeTests(unittest.TestCase):
    def test_diff_is_frozen(self):
        diff = diff_catalog("k", declared=["A"], actual=[])
        with self.assertRaises(Exception):
            diff.key = "other"  # type: ignore[misc]

    def test_to_dict_keys_are_stable(self):
        diff = diff_catalog("k", declared=["A"], actual=[])
        self.assertEqual(
            sorted(diff.to_dict()),
            sorted(
                [
                    "key",
                    "model",
                    "natural_key",
                    "checksum",
                    "in_sync",
                    "declared_count",
                    "present_count",
                    "missing_count",
                    "extra_count",
                    "inactive_count",
                    "actual_count",
                    "missing",
                    "extra",
                    "inactive",
                    "apply_supported",
                    "remedy",
                ]
            ),
        )

    def test_is_constructible_directly_for_synthetic_fixtures(self):
        diff = CatalogDiff(
            key="k",
            declared=("A",),
            actual=(),
            missing=("A",),
            extra=(),
            inactive=(),
            checksum="sha256:x",
        )
        self.assertEqual(diff.present_count, 0)
        self.assertFalse(diff.in_sync)


if __name__ == "__main__":
    unittest.main()
