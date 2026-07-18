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
    GRADING_SCALES,
    REGISTRY_SCALE_TYPE_MAP,
    cohort_t_scores,
    format_grade_band,
)
from apps.evals.grading_provisioning import _VALID_SCALE_TYPES, _normalize_scale_type
from apps.evals.grading_wizard_kernel import _SCALE_TYPE_MAP
from apps.evals.models import EXTENDED_GRADE_BANDS, GRADING_SCALE_BANDS, GradingScale

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_gate_module():
    """The registries coverage gate loaded by path (its real SOT for REQUIRED_CODES
    and the pure ``render_coverage_gaps`` helper)."""
    gate = REPO_ROOT / "scripts" / "verify_grading_scale_registry_coverage.py"
    spec = importlib.util.spec_from_file_location("_gscov", gate)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _gate_required_codes() -> tuple[str, ...]:
    """The registries coverage gate's REQUIRED_CODES, loaded by path (its real SOT)."""
    return tuple(_load_gate_module().REQUIRED_CODES)


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

    def test_all_world_scales_operationally_resolvable(self):
        # End-to-end smell test: every registry code -> a DISTINCT operational scale_type
        # (no two world scales collapse onto the same engine type). The bridge must stay
        # 1:1 with the registry's REQUIRED_CODES — it grew from 9 to the full world set
        # when the four international curriculum scales (UK GCSE / IB / German / CBSE,
        # plus French + US) were wired through the operational engine.
        required = _gate_required_codes()
        self.assertEqual(len(REGISTRY_SCALE_TYPE_MAP), len(required))
        self.assertEqual(
            len(set(REGISTRY_SCALE_TYPE_MAP.values())),
            len(REGISTRY_SCALE_TYPE_MAP),
        )


class CoverageGateRenderPathMustFireTests(SimpleTestCase):
    """The coverage gate must be ABLE to fail on a real render gap (must-fire).

    The old gate seeded the registry then asserted its own write (``missing`` could
    never be non-empty) and validated ``metadata['boundary_map']`` — a table NO report
    card renders (read only by the gate + the runtime grading-matrix JSON payload). The
    de-tautologized gate instead points its RENDER COVERAGE at the exact tables the
    report-card path reads (``resolve_extended_band_label`` / ``EXTENDED_GRADE_BANDS``
    + the ``GRADING_SCALE_BANDS`` / ``GRADING_SCALES`` coarse fallback), bridged from
    the registry code via ``REGISTRY_SCALE_TYPE_MAP``. These tests pin that the gate's
    pure ``render_coverage_gaps`` helper PASSES on the real maps and FAILS on an
    injected gap — the property the tautological gate structurally lacked.
    """

    def _gaps(self, *, registry_map=None, aw_map=None, scales=None, extended=None, bands=None):
        mod = _load_gate_module()
        return mod.render_coverage_gaps(
            _gate_required_codes(),
            registry_map if registry_map is not None else REGISTRY_SCALE_TYPE_MAP,
            aw_map if aw_map is not None else ASSESSMENT_WEIGHTS_SCALE_MAP,
            scales if scales is not None else set(GRADING_SCALES.keys()),
            extended if extended is not None else EXTENDED_GRADE_BANDS,
            bands if bands is not None else GRADING_SCALE_BANDS,
        )

    def test_clean_tree_has_zero_render_gaps(self):
        # Calibration: every registry code a school can pick renders a real band table.
        self.assertEqual(self._gaps(), [])

    def test_unmapped_registry_code_is_a_gap(self):
        # A registry scale a school can PICK but with no operational/render home.
        broken = dict(REGISTRY_SCALE_TYPE_MAP)
        broken.pop("IB_1_7")
        self.assertIn("IB_1_7", self._gaps(registry_map=broken))

    def test_scale_type_without_score_axis_is_a_gap(self):
        # scale_type not in GRADING_SCALE_BANDS → the model has no score axis to render.
        broken = dict(REGISTRY_SCALE_TYPE_MAP)
        broken["IB_1_7"] = "nonexistent_scale_type"
        self.assertIn("IB_1_7", self._gaps(registry_map=broken))

    def test_no_rich_and_no_coarse_display_scale_is_a_gap(self):
        # A numeric scale with no rich band table whose coarse display scale is missing
        # from GRADING_SCALES would silently render the 0–20 fallback for a foreign scale.
        broken_aw = dict(ASSESSMENT_WEIGHTS_SCALE_MAP)
        broken_aw["french_0_20"] = "no-such-display-scale"  # FRENCH_0_20 is not in EXTENDED
        self.assertIn("FRENCH_0_20", self._gaps(aw_map=broken_aw))

    def test_rich_scale_survives_missing_coarse_display_scale(self):
        # A rich extended-band scale (IB) still renders via EXTENDED_GRADE_BANDS even if
        # its coarse display alias is gone — so it is NOT a gap (no false positive).
        broken_aw = dict(ASSESSMENT_WEIGHTS_SCALE_MAP)
        broken_aw["ib_1_7"] = "no-such-display-scale"
        self.assertNotIn("IB_1_7", self._gaps(aw_map=broken_aw))
