"""Stdlib coverage for verify_grading_scale_registry_coverage `_boundary_display_ok`.

The Django phase (querying GradeScaleRegistry) runs in CI's django-tests job via
`--strict`. This locks the pure display-assertion logic added to prove that a
scale's band table does not merely EXIST but renders a display label for an
in-range score (labeled bands, no coverage hole) — the "display per scale" leg of
metric 3, with no Django DB.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import verify_grading_scale_registry_coverage as v  # noqa: E402


class BoundaryDisplayTests(unittest.TestCase):
    def _bands(self):
        # A well-formed WAEC-style band table covering 0..100.
        return [
            {"grade": "A1", "min": 75, "max": 100},
            {"grade": "B2", "min": 70, "max": 74.99},
            {"grade": "C6", "min": 50, "max": 69.99},
            {"grade": "F9", "min": 0, "max": 49.99},
        ]

    def test_labeled_bands_covering_range_ok(self):
        self.assertTrue(v._boundary_display_ok(self._bands()))

    def test_two_labeled_bands_ok(self):
        self.assertTrue(v._boundary_display_ok([
            {"grade": "Pass", "min": 50, "max": 100},
            {"grade": "Fail", "min": 0, "max": 49.99},
        ]))

    def test_unlabeled_band_fails(self):
        bands = self._bands()
        bands[1]["grade"] = ""  # blank display label
        self.assertFalse(v._boundary_display_ok(bands))

    def test_missing_grade_key_fails(self):
        bands = self._bands()
        del bands[0]["grade"]
        self.assertFalse(v._boundary_display_ok(bands))

    def test_coverage_hole_at_midrange_fails(self):
        # 0..100 range, but nothing covers the midpoint (50) → an in-range mark
        # would render blank.
        self.assertFalse(v._boundary_display_ok([
            {"grade": "Top", "min": 80, "max": 100},
            {"grade": "Bottom", "min": 0, "max": 40},
        ]))

    def test_single_band_fails(self):
        self.assertFalse(v._boundary_display_ok([{"grade": "Only", "min": 0, "max": 100}]))

    def test_non_numeric_bounds_fail(self):
        self.assertFalse(v._boundary_display_ok([
            {"grade": "A", "min": "x", "max": "y"},
            {"grade": "B", "min": 0, "max": 5},
        ]))


if __name__ == "__main__":
    unittest.main()
