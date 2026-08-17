"""Migration Cloud B5 — the live-connector import path resolved entities by EXACT
string membership, so a source's own spelling silently lost a whole domain.

``ConnectorAdapter.supports_entity`` was ``entity_type in self.list_entities()``, and
``discover_entities`` did ``if not adapter.supports_entity(...): continue``. A vendor
reporting ``"Students"`` / ``"Student"`` / ``"ReportCards"`` therefore matched nothing and
the loop dropped that entity with NO warning, NO error and NO quarantine row — the
operator saw a clean discovery result that was simply missing data. The FILE ingest path
had already been fixed to score by containment (commit 10dd50540); the connector path was
the deferred half (B5).

Two properties are locked here:

1. RECALL — a source's own spelling resolves onto our canonical key: case, punctuation and
   separators, camelCase (which REST/OneRoster vendors use), and singular/plural.
2. HONESTY — a name we cannot resolve is REPORTED, not skipped. Silence was the actual
   defect; a warning is what makes a missing domain visible.

And one deliberate NON-property: resolution is morphological ONLY. ``ENTITY_TYPES``
contains both ``grades`` (grade LEVELS) and ``marks`` (scores), so a semantic synonym
table would silently route scores into levels — turning a recall bug into a correctness
bug. Unknown names are surfaced, never guessed.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.migration_cloud.connectors.base import (
    ENTITY_TYPES,
    ConnectorCapabilities,
    EntityPreview,
    normalize_entity_key,
    resolve_entity_type,
)


class EntityTypeResolutionTests(SimpleTestCase):
    def test_vendor_spellings_resolve_to_the_canonical_key(self):
        cases = {
            "Students": "students",
            "STUDENT": "students",
            "student": "students",
            "Guardian": "guardians",
            "Teachers": "teachers",
            "Enrollment": "enrollments",
            "Classes": "classes",
            "class": "classes",
            "Report Cards": "report_cards",
            "report-cards": "report_cards",
            "ReportCards": "report_cards",   # camelCase — REST / OneRoster shape
            "reportCards": "report_cards",
            "AcademicYears": "academic_years",
            "academic year": "academic_years",
            "  payments  ": "payments",
        }
        for reported, expected in cases.items():
            with self.subTest(reported=reported):
                self.assertEqual(resolve_entity_type(reported), expected)

    def test_grade_levels_and_marks_are_never_conflated(self):
        """The correctness trap: ENTITY_TYPES holds BOTH, so no synonym guessing."""
        self.assertEqual(resolve_entity_type("Grades"), "grades")
        self.assertEqual(resolve_entity_type("Marks"), "marks")
        self.assertNotEqual(resolve_entity_type("Marks"), "grades")

    def test_every_canonical_name_resolves_to_itself(self):
        """No entity's singular form may shadow another entity's canonical name."""
        mismatched = {e: resolve_entity_type(e) for e in ENTITY_TYPES if resolve_entity_type(e) != e}
        self.assertEqual(mismatched, {})

    def test_unknown_and_empty_names_resolve_to_none(self):
        for reported in ("Cafeteria Ledger", "widgets", "", None, "   "):
            with self.subTest(reported=reported):
                self.assertIsNone(resolve_entity_type(reported))

    def test_normalize_is_stable_and_separator_agnostic(self):
        for variant in ("report_cards", "Report Cards", "report-cards", "ReportCards"):
            self.assertEqual(normalize_entity_key(variant), "report_cards")


class _FakeAdapter:
    """Minimal adapter: reports the SOURCE's spellings, serves canonical keys."""

    def __init__(self, reported):
        self._reported = list(reported)
        self.extracted: list[str] = []

    def discover_capabilities(self, *, source_url, credentials):
        return ConnectorCapabilities(supported_entities=list(self._reported))

    def list_entities(self):
        return list(ENTITY_TYPES)

    def supports_entity(self, entity_type):
        from apps.migration_cloud.connectors.base import ConnectorAdapter

        return ConnectorAdapter.supports_entity(self, entity_type)

    def extract_entity(self, entity_type, *, source_url, credentials, limit=25):
        self.extracted.append(entity_type)
        return EntityPreview(entity_type=entity_type, estimated_count=7)


class DiscoveryRecallAndHonestyTests(SimpleTestCase):
    """``discover_entities`` only reads connection.connector_profile.key + .source_url, so
    this exercises the real function against stubs — no database needed."""

    def _run(self, reported):
        from apps.migration_cloud.services import connector_discovery as cd

        adapter = _FakeAdapter(reported)
        connection = SimpleNamespace(
            connector_profile=SimpleNamespace(key="fake"),
            source_url="https://sis.example.test",
        )
        with patch.object(cd, "get_connector", return_value=adapter), patch.object(
            cd, "retrieve_source_credential_for_runtime", return_value={}
        ):
            return cd.discover_entities(connection=connection), adapter

    def test_vendor_spelling_is_imported_under_its_canonical_key(self):
        result, adapter = self._run(["Students", "ReportCards", "Guardian"])
        # Canonical keys are what land — downstream lookups use them.
        self.assertEqual(sorted(result["entities"]), ["guardians", "report_cards", "students"])
        self.assertEqual(sorted(adapter.extracted), ["guardians", "report_cards", "students"])
        self.assertEqual(result["counts"]["students"], 7)
        self.assertFalse(
            [w for w in result["warnings"] if "does not map" in w],
            "a resolvable vendor spelling must not warn",
        )

    def test_unresolvable_entity_is_reported_not_silently_skipped(self):
        """The core B5 fix: silence was the defect."""
        result, adapter = self._run(["Students", "Cafeteria Ledger"])
        self.assertEqual(result["entities"], ["students"])
        self.assertNotIn("Cafeteria Ledger", adapter.extracted)
        unmapped = [w for w in result["warnings"] if "Cafeteria Ledger" in w]
        self.assertEqual(len(unmapped), 1, result["warnings"])
        self.assertIn("NOT imported", unmapped[0])

    def test_one_unmappable_entity_does_not_cost_the_others(self):
        result, _adapter = self._run(["widgets", "Students", "Marks", "Grades"])
        self.assertEqual(sorted(result["entities"]), ["grades", "marks", "students"])
