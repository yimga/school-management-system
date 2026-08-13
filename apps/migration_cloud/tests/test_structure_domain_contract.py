"""Fast, DB-free contracts for the SPLIT structure-provisioning domain.

Guards the wiring the end-to-end test (test_transfer_split_structure) depends
on but which would otherwise fail silently: the lander must be registered, the
accelerator must identity-map every structure column (else it drops to
custom_fields), the pipeline must run `structure` BEFORE students/enrollment/
grades, splits (only) must carry the domain, and minted codes must never reuse
the source's globally-unique code.
"""
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.migration_cloud.accelerators.runmycampus_canonical import (
    CANONICAL_FILENAME_TO_DOMAIN,
    DOMAIN_CANONICAL_HEADERS,
)
from apps.migration_cloud.landers import get_lander
# _slug_upper's canonical home is _helpers (structure_lander's duplicate + its
# duplicate _mint_code body were collapsed onto the shared, UUID-safe minter).
from apps.migration_cloud.landers._helpers import _slug_upper
from apps.migration_cloud.landers.structure_lander import _mint_code
from apps.migration_cloud.orchestrator import _DEPENDENCY_WAVES

# The columns the exporter emits for the structure domain — the accelerator must
# identity-map all of them or the lander never receives them.
STRUCTURE_COLUMNS = {
    "academic_year", "year_start", "year_end", "year_is_active",
    "term", "term_label", "term_position", "term_start", "term_end",
    "department", "classroom", "specialty", "subject", "coefficient",
    "teacher_ref", "teacher_first_name", "teacher_last_name", "teacher_email",
}


def _wave_index(domain: str) -> int:
    for i, wave in enumerate(_DEPENDENCY_WAVES):
        if domain in wave:
            return i
    return len(_DEPENDENCY_WAVES)  # catch-all (would run last)


class StructureWiringTest(SimpleTestCase):
    def test_lander_is_registered(self):
        lander = get_lander("structure")
        self.assertIsNotNone(lander)
        self.assertEqual(lander.domain, "structure")

    def test_accelerator_maps_filename_and_every_column(self):
        self.assertEqual(CANONICAL_FILENAME_TO_DOMAIN.get("structure.csv"), "structure")
        headers = DOMAIN_CANONICAL_HEADERS["structure"]
        missing = [c for c in STRUCTURE_COLUMNS if c not in headers]
        self.assertEqual(missing, [], f"columns dropped to custom_fields: {missing}")

    def test_structure_runs_before_students_enrollment_grades(self):
        s = _wave_index("structure")
        self.assertLess(s, _wave_index("students"))
        self.assertLess(s, _wave_index("enrollment"))
        self.assertLess(s, _wave_index("grades"))
        # And it must NOT fall into the catch-all last wave.
        self.assertLess(s, len(_DEPENDENCY_WAVES) - 1)


class SplitScopingTest(SimpleTestCase):
    def _domains(self, kind):
        from apps.people.models_school_batch import SchoolTransferBatch
        from apps.people.school_batch_service import _batch_domains

        k = None if kind is None else getattr(SchoolTransferBatch.Kind, kind)
        batch = None if kind is None else SimpleNamespace(kind=k)
        return _batch_domains(batch)

    def test_split_prepends_structure_first(self):
        domains = self._domains("SPLIT")
        self.assertEqual(domains[0], "structure")

    def test_merge_does_not_carry_structure(self):
        self.assertNotIn("structure", self._domains("MERGE"))

    def test_default_no_batch_has_no_structure(self):
        self.assertNotIn("structure", self._domains(None))


class _StubQS:
    def exists(self):
        return False


class _StubMgr:
    def filter(self, **kw):
        return _StubQS()


class _StubModel:
    """Stands in for a Django model whose ``code`` is never already taken."""

    objects = _StubMgr()


class MintCodeTest(SimpleTestCase):
    def test_slug_upper_strips_and_caps(self):
        self.assertEqual(_slug_upper("Form 4A"), "FORM4A")
        self.assertEqual(_slug_upper(""), "X")

    def test_minted_code_is_target_scoped_and_not_source(self):
        school = SimpleNamespace(pk=42)
        code = _mint_code(
            prefix="CLS", name="Form 4A", school=school, model=_StubModel
        )
        # Target-scoped (carries the school id) and deterministic.
        self.assertTrue(code.startswith("CLS42-"))
        self.assertIn("FORM4A", code)
        self.assertNotEqual(code, "F4A-SPLIT-SRC")  # never the source's code
        self.assertEqual(
            code,
            _mint_code(prefix="CLS", name="Form 4A", school=school, model=_StubModel),
        )
