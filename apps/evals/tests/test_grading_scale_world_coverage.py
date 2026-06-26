"""Phase C of the world-scale bridge: the T-score (cohort-relative) + the KEYSTONE
coverage test proving the operational engine now grades on every world scale the
platform catalog advertises.

T-score is honest: a single mark has no T in isolation, so cohort_t_scores computes
it over the whole cohort (real statistics), and the scale is registered like the rest.
The keystone test (test_every_registry_code_is_operational) makes "the catalog claims
N scales" and "teachers can grade on N scales" provably the SAME set.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from django.test import SimpleTestCase

from apps.evals.grading import (
    ASSESSMENT_WEIGHTS_SCALE_MAP,
    REGISTRY_SCALE_TYPE_MAP,
    cohort_t_scores,
    format_grade_band,
)
from apps.evals.grading_provisioning import _VALID_SCALE_TYPES, _normalize_scale_type
from apps.evals.grading_wizard_kernel import _SCALE_TYPE_MAP
from apps.evals.models import EXTENDED_GRADE_BANDS, GRADING_SCALE_BANDS, GradingScale

REPO_ROOT = Path(__file__).resolve().parents[3]


def _gate_required_codes() -> tuple[str, ...]:
    """The registries coverage gate's REQUIRED_CODES, loaded by path (its real SOT)."""
    gate = REPO_ROOT / "scripts" / "verify_grading_scale_registry_coverage.py"
    spec = importlib.util.spec_from_file_location("_gscov", gate)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return tuple(module.REQUIRED_CODES)


class CohortTScoreTests(SimpleTestCase):
    def test_two_point_cohort(self):
        # mean 50, pstdev 10 -> T(40)=40, T(60)=60.
        self.assertEqual(cohort_t_scores([40, 60]), [40.0, 60.0])

    def test_midpoint_is_fifty_and_symmetric(self):
        out = cohort_t_scores([0, 25, 50, 75, 100])
        self.assertEqual(out[2], 50.0)            # the mean maps to T=50
        self.assertAlmostEqual(out[0] + out[4], 100.0, places=1)  # symmetric about 50

    def test_zero_spread_and_too_small_cohort(self):
        self.assertEqual(cohort_t_scores([50, 50, 50]), [50.0, 50.0, 50.0])
        self.assertEqual(cohort_t_scores([70]), [50.0])  # <2 graded -> neutral 50
        self.assertEqual(cohort_t_scores([]), [])

    def test_none_marks_preserved_in_order(self):
        self.assertEqual(cohort_t_scores([None, 40, 60]), [None, 40.0, 60.0])


class StandardScoreTRegistrationTests(SimpleTestCase):
    def test_registered_but_not_a_fixed_band_family(self):
        self.assertIn("standard_score_t", _VALID_SCALE_TYPES)
        self.assertEqual(GRADING_SCALE_BANDS["standard_score_t"]["score_scale"], 100)
        self.assertEqual(ASSESSMENT_WEIGHTS_SCALE_MAP["standard_score_t"], "0-100")
        # T-score is NOT a fixed-band family — it must not be faked with static bands.
        self.assertNotIn("standard_score_t", EXTENDED_GRADE_BANDS)
        self.assertEqual(_normalize_scale_type("t_score"), "standard_score_t")
        self.assertEqual(_SCALE_TYPE_MAP["hensachi"], "standard_score_t")

    def test_single_score_display_falls_back_to_coarse_letter(self):
        # No theatre: one raw mark shows its coarse letter, not a fabricated T.
        self.assertEqual(format_grade_band("standard_score_t", 70), "C")


class WorldScaleCoverageKeystoneTests(SimpleTestCase):
    """The bridge is only real if the catalog set == the operational set."""

    def test_every_registry_code_is_operational(self):
        required = set(_gate_required_codes())
        # 1. The bridge map covers exactly the registry's required world-scale codes.
        self.assertEqual(
            set(REGISTRY_SCALE_TYPE_MAP.keys()),
            required,
            "REGISTRY_SCALE_TYPE_MAP and the coverage gate's REQUIRED_CODES disagree — "
            "a world scale exists in the catalog with no operational home (or vice versa).",
        )
        valid_scale_type_values = set(GradingScale.ScaleType.values)
        # 2. Each registry code maps to a fully-wired operational scale_type.
        for code, scale_type in REGISTRY_SCALE_TYPE_MAP.items():
            self.assertIn(scale_type, _VALID_SCALE_TYPES, msg=code)
            self.assertIn(scale_type, GRADING_SCALE_BANDS, msg=code)
            self.assertIn(scale_type, ASSESSMENT_WEIGHTS_SCALE_MAP, msg=code)
            self.assertIn(scale_type, valid_scale_type_values, msg=code)

    def test_all_nine_operationally_resolvable(self):
        # End-to-end smell test: 9 distinct registry codes -> 9 distinct operational types.
        self.assertEqual(len(REGISTRY_SCALE_TYPE_MAP), 9)
        self.assertEqual(len(set(REGISTRY_SCALE_TYPE_MAP.values())), 9)
