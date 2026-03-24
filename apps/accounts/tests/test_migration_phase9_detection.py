"""Phase 9 — Migration Cloud source detection + confidence helpers."""

from django.test import SimpleTestCase

from apps.accounts.migration_services import (
    compute_migration_confidence,
    detect_source_system_from_headers,
)


class MigrationSourceDetectionTests(SimpleTestCase):
    def test_empty_headers_other(self):
        d = detect_source_system_from_headers([])
        self.assertEqual(d["suggested_system"], "other")
        self.assertEqual(d["score"], 0.0)

    def test_powerschool_signals(self):
        d = detect_source_system_from_headers(
            ["DCID", "LastFirst", "Student_Number", "Grade_Level"]
        )
        self.assertEqual(d["suggested_system"], "powerschool")
        self.assertGreaterEqual(d["score"], 0.34)

    def test_infinite_campus_signals(self):
        d = detect_source_system_from_headers(
            ["studentStateIdentifier", "calId", "firstName"]
        )
        self.assertEqual(d["suggested_system"], "infinite_campus")

    def test_confidence_high_clean(self):
        c = compute_migration_confidence(
            10,
            {"error_count": 0, "created": 10, "updated": 0},
            {"duplicates": [], "missing_required": [], "invalid_refs": []},
        )
        self.assertEqual(c["band"], "high")
        self.assertGreaterEqual(c["score"], 0.85)

    def test_confidence_low_many_errors(self):
        c = compute_migration_confidence(
            10,
            {"error_count": 8, "created": 0, "updated": 0},
            {"duplicates": [{"row": 1}], "missing_required": [], "invalid_refs": []},
        )
        self.assertIn(c["band"], ("low", "medium"))
