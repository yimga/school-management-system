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


class GradeScaleSeedCountryCodeTests(TestCase):
    """The country_code column is the resolver's ONLY per-tenant differentiator.

    Steps 1-2 of ``resolve_grade_scale_for_tenant`` need override rows that only
    an RMC operator can create and step 3 is a platform-wide singleton, so if the
    seeders drop ``country_code`` the country fallback matches nothing and every
    tenant resolves to the same scale (or to None).
    """

    def test_seed_writes_country_code_for_every_row_that_declares_one(self):
        from apps.registries.models import GradeScaleRegistry

        declared = {
            row["code"]: row["country_code"]
            for row in GRADE_SCALE_SEED_DEFAULTS
            if row.get("country_code")
        }
        # Guard against a vacuous pass if the constant ever loses the key.
        self.assertGreaterEqual(len(declared), 5, "seed constant declares no country_code")

        ensure_grade_scale_seed()
        for code, country_code in declared.items():
            self.assertEqual(
                GradeScaleRegistry.objects.get(code=code).country_code,
                country_code,
                f"{code} was seeded without its country_code",
            )

    def test_country_fallback_resolves_a_scale_for_a_us_school(self):
        from apps.platform_runtime.models import RuntimeDefaults
        from apps.registries.grade_scale_resolver import resolve_grade_scale_for_tenant
        from apps.registries.models import TenantGradeScaleOverride
        from apps.schools.models import School

        ensure_grade_scale_seed()
        school = School.objects.create(
            name="Country Fallback High",
            subdomain="country-fallback-high",
            country_code="US",
        )
        # Prove steps 1-3 cannot supply the answer, so step 4 is what is measured.
        self.assertFalse(TenantGradeScaleOverride.objects.filter(school=school).exists())
        RuntimeDefaults.objects.update(default_grading_scale="")

        resolved = resolve_grade_scale_for_tenant(school)
        self.assertIsNotNone(
            resolved, "country fallback matched no row — country_code was never seeded"
        )
        self.assertEqual(resolved.code, "US_LETTER")
