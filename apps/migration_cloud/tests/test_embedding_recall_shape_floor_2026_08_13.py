"""Embedding-recall value-shape floor (G4).

The mapper's embedding-recall layer short-circuits to a previously-accepted
mapping WITHOUT the value-shape check the token layer applies. A stale or
mistaken recalled decision (``USERNAME -> date_of_birth`` — "abel.esakenong"
into a date column) was therefore applied at high confidence and crashed the
date transformer / corrupted the field. These pin the floor: a recall onto a
strict-typed field is only accepted when the source values actually fit it.
"""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase

from apps.migration_cloud import mapper as mapper_mod
from apps.migration_cloud.mapper import (
    _looks_dateish,
    _looks_numeric,
    _map_one_column,
    _samples_fit_value_type,
)


class SamplesFitValueTypeTests(SimpleTestCase):
    def test_free_text_types_always_fit(self):
        for vt in ("string", "email", "phone", "enum"):
            self.assertTrue(_samples_fit_value_type(["abel.esakenong"], vt))

    def test_date_field_rejects_usernames(self):
        self.assertFalse(
            _samples_fit_value_type(["abel.esakenong", "david.ekeke"], "date")
        )

    def test_date_field_accepts_dates(self):
        self.assertTrue(
            _samples_fit_value_type(["2012-11-16", "2012-08-31"], "date")
        )
        self.assertTrue(_samples_fit_value_type(["16/11/2012"], "date"))
        self.assertTrue(_samples_fit_value_type(["2011"], "date"))  # bare year

    def test_numeric_field_rejects_text(self):
        self.assertFalse(_samples_fit_value_type(["Catholic", "Muslim"], "int"))

    def test_numeric_field_accepts_numbers(self):
        self.assertTrue(_samples_fit_value_type(["12", "3.5"], "decimal"))
        self.assertTrue(_samples_fit_value_type(["50 000 FCFA"], "currency"))

    def test_empty_samples_do_not_block(self):
        self.assertTrue(_samples_fit_value_type([], "date"))
        self.assertTrue(_samples_fit_value_type(["", "  "], "int"))

    def test_looks_helpers(self):
        self.assertTrue(_looks_numeric("241,904"))
        self.assertFalse(_looks_numeric("abel"))
        self.assertTrue(_looks_dateish("2012-11-16"))
        self.assertTrue(_looks_dateish("12 Jan 2020"))
        self.assertFalse(_looks_dateish("abel.esakenong"))


class RecallFloorIntegrationTests(TestCase):
    """A recalled USERNAME -> date_of_birth is rejected by the floor and never
    lands as the date field (falls through to custom field — no crash)."""

    def test_bad_recall_is_rejected(self):
        from apps.migration_cloud.models import (
            BundleStatus, IntakeMethod, MigrationArtifact, MigrationBundle,
        )
        from apps.migration_cloud.ontology import iter_canonical_fields

        bundle = MigrationBundle.objects.create(
            label="r", intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="recall-floor", status=BundleStatus.MAPPED, school=None,
        )
        art = MigrationArtifact.objects.create(
            bundle=bundle, path_within_bundle="s.csv", filename="students.csv",
            detected_format="csv", byte_size=1, sha256="0" * 64,
        )
        col = {"name": "USERNAME", "normalized": "username",
               "inferred_type": "string", "samples": ["abel.esakenong", "david.ekeke"]}
        canonical_fields = list(iter_canonical_fields("students"))

        original_recall = mapper_mod.ai_bridge.recall_mapping_decision
        original_propose = mapper_mod.ai_bridge.propose_field_mapping
        mapper_mod.ai_bridge.recall_mapping_decision = lambda **kw: {
            "canonical_field": "date_of_birth", "confidence": 0.98,
        }
        mapper_mod.ai_bridge.propose_field_mapping = lambda **kw: None
        try:
            mapping = _map_one_column(col, canonical_fields, "students", art, 0.6)
        finally:
            mapper_mod.ai_bridge.recall_mapping_decision = original_recall
            mapper_mod.ai_bridge.propose_field_mapping = original_propose

        self.assertNotEqual(
            mapping.canonical_field, "date_of_birth",
            "floor must reject a date recall for non-date username values",
        )
