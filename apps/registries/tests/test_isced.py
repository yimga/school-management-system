"""M30 foundation increment — ISCED progression spine tests.

Three layers, each a must-fire against the pre-M30 tree:

* Pure helpers (``apps.registries.isced``) — fail-before: the module does not
  exist, so the import at the top of this file raises ``ImportError`` and every
  test in the file errors out.
* Registry seed backfill — fail-before: ``EducationLevelRegistry`` has no
  ``isced_level`` / ``tier`` fields and no ``EARLY_CHILDHOOD`` row.
* Field contract — fail-before: without the 0-8 validator, ``isced_level=9``
  would save without complaint.
"""

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from apps.registries import isced
from apps.registries.models import EducationLevelRegistry
from apps.registries.services import ensure_taxonomy_seed


class IscedPureHelperTests(SimpleTestCase):
    """No DB — pure functions over ISCED 2011 levels 0-8."""

    def test_next_isced_level_chain(self):
        self.assertEqual(isced.next_isced_level(0), 1)
        self.assertEqual(isced.next_isced_level(3), 4)
        self.assertIsNone(isced.next_isced_level(8))

    def test_next_isced_level_full_ladder(self):
        # 0->1->...->7->8, top of ladder returns None.
        chain = [0]
        while (nxt := isced.next_isced_level(chain[-1])) is not None:
            chain.append(nxt)
        self.assertEqual(chain, [0, 1, 2, 3, 4, 5, 6, 7, 8])

    def test_tier_for_isced_mapping(self):
        self.assertEqual(isced.tier_for_isced(0), "EARLY_CHILDHOOD")
        self.assertEqual(isced.tier_for_isced(2), "K12")
        self.assertEqual(isced.tier_for_isced(6), "TERTIARY")

    def test_tier_for_isced_boundaries(self):
        # 1-4 are K12 (4 = post-secondary non-tertiary boundary → K12);
        # 5-8 are TERTIARY.
        for level in (1, 2, 3, 4):
            self.assertEqual(isced.tier_for_isced(level), "K12")
        for level in (5, 6, 7, 8):
            self.assertEqual(isced.tier_for_isced(level), "TERTIARY")

    def test_isced_level_name(self):
        self.assertEqual(isced.isced_level_name(3), "Upper secondary")
        self.assertEqual(isced.isced_level_name(0), "Early childhood")
        self.assertEqual(isced.isced_level_name(8), "Doctoral")

    def test_out_of_range_raises(self):
        for bad in (-1, 9, 42):
            with self.assertRaises(ValueError):
                isced.isced_level_name(bad)
            with self.assertRaises(ValueError):
                isced.next_isced_level(bad)
            with self.assertRaises(ValueError):
                isced.tier_for_isced(bad)

    def test_tier_constants_match_model_choices(self):
        # Load-bearing contract: the pure module's tier codes MUST equal the
        # model's Tier TextChoices values (they are kept in two places by
        # design — the model can't import the pure module's constants without
        # circularity risk, so a test seals the equivalence).
        self.assertEqual(
            isced.TIER_EARLY_CHILDHOOD,
            EducationLevelRegistry.Tier.EARLY_CHILDHOOD.value,
        )
        self.assertEqual(isced.TIER_K12, EducationLevelRegistry.Tier.K12.value)
        self.assertEqual(
            isced.TIER_TERTIARY, EducationLevelRegistry.Tier.TERTIARY.value
        )

    def test_span_for_level_code(self):
        self.assertEqual(isced.ISCED_SPAN_FOR_LEVEL_CODE["PRIMARY"], 1)
        self.assertEqual(isced.ISCED_SPAN_FOR_LEVEL_CODE["SECONDARY"], 2)
        self.assertEqual(isced.ISCED_SPAN_FOR_LEVEL_CODE["TERTIARY"], 6)


class IscedRegistryBackfillTests(TestCase):
    """DB — the seed writes isced_level + tier and the EARLY_CHILDHOOD row."""

    def test_seed_backfills_tertiary_isced_and_tier(self):
        ensure_taxonomy_seed()
        tertiary = EducationLevelRegistry.objects.get(code="TERTIARY")
        self.assertEqual(tertiary.isced_level, 6)
        self.assertEqual(tertiary.tier, "TERTIARY")

    def test_seed_backfills_primary_and_secondary(self):
        ensure_taxonomy_seed()
        primary = EducationLevelRegistry.objects.get(code="PRIMARY")
        self.assertEqual(primary.isced_level, 1)
        self.assertEqual(primary.tier, "K12")
        secondary = EducationLevelRegistry.objects.get(code="SECONDARY")
        self.assertEqual(secondary.isced_level, 2)
        self.assertEqual(secondary.tier, "K12")

    def test_seed_creates_early_childhood_row(self):
        ensure_taxonomy_seed()
        early = EducationLevelRegistry.objects.get(code="EARLY_CHILDHOOD")
        self.assertEqual(early.isced_level, 0)
        self.assertEqual(early.tier, "EARLY_CHILDHOOD")
        self.assertEqual(early.sort_order, 5)

    def test_seed_is_idempotent(self):
        ensure_taxonomy_seed()
        ensure_taxonomy_seed()
        # No duplicates: exactly one row per canonical code.
        for code in ("EARLY_CHILDHOOD", "PRIMARY", "SECONDARY", "TERTIARY"):
            self.assertEqual(
                EducationLevelRegistry.objects.filter(code=code).count(), 1
            )
        # Values stable after a second run.
        self.assertEqual(
            EducationLevelRegistry.objects.get(code="TERTIARY").isced_level, 6
        )


class IscedFieldContractTests(TestCase):
    """DB — the 0-8 validator rejects out-of-range ISCED levels."""

    def _row(self, **overrides):
        data = {
            "code": "TEST_LEVEL",
            "global_name": "Test level",
            "sort_order": 1,
        }
        data.update(overrides)
        return EducationLevelRegistry(**data)

    def test_isced_level_9_fails_validation(self):
        with self.assertRaises(ValidationError):
            self._row(isced_level=9).full_clean()

    def test_isced_level_within_range_validates(self):
        # Boundaries 0 and 8 are valid.
        self._row(code="LVL0", isced_level=0, tier="EARLY_CHILDHOOD").full_clean()
        self._row(code="LVL8", isced_level=8, tier="TERTIARY").full_clean()

    def test_null_isced_level_is_allowed(self):
        # Nullable/blank — a row without an ISCED mapping is valid.
        self._row(code="LVL_NONE").full_clean()
