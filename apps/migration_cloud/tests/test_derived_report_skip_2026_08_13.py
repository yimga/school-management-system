"""Derived statistics reports are detected and skipped (G10).

A school's export set often includes ``school_stats`` — per-class/specialty
AGGREGATES (Total / Pass % / Passed / Male / Female), not per-entity records.
Ingesting it fabricated one phantom enrollment row per aggregate line. These
pin: the file is detected as a report, routed to the report lander, and lands
ZERO records (rows skipped, not quarantined), while a genuine roster with a
lone ``total`` column still ingests.
"""

from __future__ import annotations

import io
import types

from django.test import TestCase, TransactionTestCase

from apps.migration_cloud import artifact_blob_store as store
from apps.migration_cloud.accelerators.runmycampus_canonical import is_derived_report
from apps.migration_cloud.models import (
    ArtifactFormat,
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationBundle,
)

_STATS_HEADERS = [
    "Class", "Specialty", "Total", "Best Avg", "Worst Avg", "Passed",
    "Failed", "Pass %", "Male", "Female", "Male Passed", "Female Passed",
]
_STATS_ROWS = [
    ["Form One", "FASHION  DESIGN", "11", "0", "11", "14.5", "7.39", "72.73%", "0", "8", "8", "3"],
    ["Form One", "PLUMBING", "0", "4", "5", "14.64", "6.2", "60.00%", "3", "2", "3", "2"],
]


class IsDerivedReportTests(TestCase):
    def test_stats_file_detected(self):
        self.assertTrue(is_derived_report(_STATS_HEADERS, "school_stats_2026.xlsx"))

    def test_aggregate_columns_alone_detected(self):
        # No stats filename, but the columns are dominated by aggregates.
        self.assertTrue(is_derived_report(_STATS_HEADERS, "export.xlsx"))

    def test_genuine_roster_not_a_report(self):
        roster = ["ID", "Name", "Gender", "Date of Birth", "Class", "Total"]
        self.assertFalse(is_derived_report(roster, "students_2026.xlsx"))

    def test_grades_with_lone_total_not_a_report(self):
        self.assertFalse(
            is_derived_report(["student_external_id", "subject_code", "score", "total"],
                              "grades.csv")
        )


def _xlsx_bytes(headers, rows):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _payload(data: bytes):
    return types.SimpleNamespace(content_opener=lambda: io.BytesIO(data))


class ReportClassifyTests(TestCase):
    def test_stats_file_classifies_as_reports(self):
        from apps.migration_cloud.pipeline import advance_bundle

        data = _xlsx_bytes(_STATS_HEADERS, _STATS_ROWS)
        bundle = MigrationBundle.objects.create(
            label="stats", intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="stats-classify", status=BundleStatus.INGESTING, school=None,
        )
        art = MigrationArtifact.objects.create(
            bundle=bundle, path_within_bundle="school_stats.xlsx",
            filename="school_stats_2026.xlsx", detected_format=ArtifactFormat.XLSX,
            byte_size=len(data), sha256="0" * 64,
        )
        store.capture_artifact_blob(art, _payload(data))
        advance_bundle(bundle_id=bundle.pk, use_accelerator=True)
        bundle.refresh_from_db()
        domain = (
            ((bundle.discovery_summary or {}).get("per_artifact_domain") or {})
            .get("school_stats.xlsx", {})
            .get("domain")
        )
        self.assertEqual(domain, "reports", f"got {domain!r}")


class ReportApplyLandsZeroTests(TransactionTestCase):
    def test_report_lands_zero_records(self):
        from apps.migration_cloud.orchestrator import apply_bundle
        from apps.migration_cloud.pipeline import advance_bundle
        from apps.people.models import StudentProfile
        from apps.schools.models import School

        school = School.objects.create(name="Stats School", subdomain="stats-school")
        data = _xlsx_bytes(_STATS_HEADERS, _STATS_ROWS)
        bundle = MigrationBundle.objects.create(
            label="stats", intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="stats-apply", status=BundleStatus.INGESTING, school=school,
        )
        art = MigrationArtifact.objects.create(
            bundle=bundle, path_within_bundle="school_stats.xlsx",
            filename="school_stats_2026.xlsx", detected_format=ArtifactFormat.XLSX,
            byte_size=len(data), sha256="0" * 64,
        )
        store.capture_artifact_blob(art, _payload(data))
        advance_bundle(bundle_id=bundle.pk, use_accelerator=True)
        apply_bundle(bundle_id=bundle.pk, workers=1)
        # No phantom students/enrollment created from the aggregate lines.
        self.assertEqual(StudentProfile.objects.filter(school=school).count(), 0)
