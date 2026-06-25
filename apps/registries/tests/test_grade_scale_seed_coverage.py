"""Coverage + drift guards for the canonical grade-scale registry seed.

The world grade-scale families live in a single source of truth
(``apps.registries.services.GRADE_SCALE_SEED_DEFAULTS``). Two ways the "9 world
scales" guarantee can silently break:

  1. the seed list and the coverage gate's ``REQUIRED_CODES`` drift apart
     (someone adds a required code to the gate but forgets to seed it, or
     renames a seed code), and
  2. the seed fails to produce every required row, or duplicates one.

These lock both. The drift guard is no-DB (pure constant comparison); the seed
behaviour is a small DB test. Together with migration ``registries/0008`` (which
seeds at migrate time) and the CI-wired gate, the registry can no longer ship
empty or skewed.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from apps.registries.services import GRADE_SCALE_SEED_DEFAULTS, ensure_grade_scale_seed

REPO_ROOT = Path(__file__).resolve().parents[3]


def _gate_required_codes() -> tuple[str, ...]:
    """Load ``REQUIRED_CODES`` from the standalone coverage gate script.

    Imported by path (it lives under ``scripts/``, not an installed package) so
    the drift guard reads the gate's real SOT, not a hand-copied list.
    """
    gate_path = REPO_ROOT / "scripts" / "verify_grading_scale_registry_coverage.py"
    spec = importlib.util.spec_from_file_location("_grade_scale_gate", gate_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return tuple(module.REQUIRED_CODES)


class GradeScaleSeedDriftTests(SimpleTestCase):
    def test_seed_codes_match_gate_required_codes(self):
        seed_codes = {row["code"] for row in GRADE_SCALE_SEED_DEFAULTS}
        gate_codes = set(_gate_required_codes())
        self.assertEqual(
            seed_codes,
            gate_codes,
            "GRADE_SCALE_SEED_DEFAULTS and "
            "verify_grading_scale_registry_coverage.REQUIRED_CODES have drifted — "
            "every required code must be seeded and every seeded code required.",
        )

    def test_seed_rows_are_well_formed(self):
        codes = [row["code"] for row in GRADE_SCALE_SEED_DEFAULTS]
        self.assertEqual(len(codes), len(set(codes)), "duplicate grade-scale code in seed")
        for row in GRADE_SCALE_SEED_DEFAULTS:
            self.assertTrue(row.get("code"), msg=row)
            self.assertTrue(row.get("name"), msg=row)
            self.assertTrue(row.get("family"), msg=row)
            self.assertIsInstance(row.get("sort_order", 0), int)
            rng = row.get("range_definition")
            if rng:
                self.assertIn("min", rng, msg=row["code"])
                self.assertIn("max", rng, msg=row["code"])
                self.assertLessEqual(rng["min"], rng["max"], msg=row["code"])


class GradeScaleSeedDatabaseTests(TestCase):
    def test_seed_creates_all_required_codes_and_is_idempotent(self):
        from apps.registries.models import GradeScaleRegistry

        required = {row["code"] for row in GRADE_SCALE_SEED_DEFAULTS}

        ensure_grade_scale_seed()
        active = set(
            GradeScaleRegistry.objects.filter(code__in=required, is_active=True).values_list(
                "code", flat=True
            )
        )
        self.assertEqual(active, required, "seed did not produce every required active scale")

        count_first = GradeScaleRegistry.objects.count()
        ensure_grade_scale_seed()  # re-running must not duplicate
        self.assertEqual(
            GradeScaleRegistry.objects.count(),
            count_first,
            "ensure_grade_scale_seed is not idempotent",
        )
