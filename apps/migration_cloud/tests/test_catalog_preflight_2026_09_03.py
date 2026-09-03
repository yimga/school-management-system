"""Catalog routing preflight for tenant XLSX upload review."""

from __future__ import annotations

import io

from django.test import TestCase

from apps.migration_cloud.catalog_preflight import (
    apply_blocked_by_catalog,
    artifact_catalog_hint,
    assess_bundle_catalog_routing,
    preflight_artifact_catalog,
    review_notice,
)
from apps.migration_cloud.live_import_attention import compose_live_import
from apps.migration_cloud.models import (
    ArtifactFormat,
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationBundle,
)
from apps.schools.models import School


def _xlsx_profile(*, headers: list[str], rows: list[tuple]) -> dict:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(list(row))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class CatalogPreflightArtifactTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Preflight School",
            subdomain="preflight-school",
            country_code="CM",
            settings={"grading": {"curriculum_tracks": ["vocational_trade"]}},
        )
        self.bundle = MigrationBundle.objects.create(
            label="preflight",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="preflight-bundle",
            status=BundleStatus.MAPPED,
            school=self.school,
        )

    def _artifact(
        self,
        *,
        filename: str,
        domain: str,
        headers: list[str],
        rows: list[tuple],
    ) -> MigrationArtifact:
        raw = _xlsx_profile(headers=headers, rows=rows)
        art = MigrationArtifact.objects.create(
            bundle=self.bundle,
            path_within_bundle=filename,
            filename=filename,
            detected_format=ArtifactFormat.XLSX,
            byte_size=len(raw),
            sha256="a" * 64,
            assigned_domain=domain,
            inferred_domain=[{"domain": domain, "confidence": 0.9}],
            profile={
                "format": "xlsx",
                "columns": [
                    {
                        "name": h,
                        "normalized": h.lower(),
                        "samples": [str(r[i]) for r in rows[:3] if i < len(r)],
                    }
                    for i, h in enumerate(headers)
                ],
            },
        )
        return art

    def test_subject_catalog_tagged_specialties_is_critical_and_blocks(self):
        art = self._artifact(
            filename="subjects.xlsx",
            domain="specialties",
            headers=["TITLE", "DESCRIPTION", "CATEGORY", "COEF"],
            rows=[
                ("OHADA FINANCIAL ACCOUNTING", "desc", "Professional", "6"),
            ],
        )
        finding = preflight_artifact_catalog(art, school=self.school)
        self.assertEqual(finding["severity"], "critical")
        report = assess_bundle_catalog_routing(self.bundle)
        self.assertTrue(report["blocking"])
        blocked, _ = apply_blocked_by_catalog(
            self.bundle, confirmed=True, acknowledged=False
        )
        self.assertTrue(blocked)
        blocked2, _ = apply_blocked_by_catalog(
            self.bundle, confirmed=True, acknowledged=True
        )
        self.assertFalse(blocked2)

    def test_curriculum_reasoning_links_professional_subject_to_filiere(self):
        self._artifact(
            filename="specialties.xlsx",
            domain="specialties",
            headers=["NAME", "CODE", "DEPARTMENT"],
            rows=[("ELECTRICAL POWER SYSTEMS", "EPS", "ELECTRICAL")],
        )
        self._artifact(
            filename="subjects.xlsx",
            domain="academics",
            headers=["TITLE", "CATEGORY", "COEF"],
            rows=[("ELECTRICAL CIRCUIT THEORY", "Professional", "4")],
        )
        report = assess_bundle_catalog_routing(self.bundle)
        codes = report.get("specialty_codes_seen") or []
        self.assertIn("EPS", codes)
        links = report.get("curriculum_links") or []
        self.assertTrue(any("EPS" in (l.get("suggested_specialty_codes") or []) for l in links))

    def test_coef_without_category_warns_on_cm_academics(self):
        art = self._artifact(
            filename="subjects.xlsx",
            domain="academics",
            headers=["TITLE", "COEF"],
            rows=[("WORKSHOP TECHNIQUES", "6")],
        )
        finding = preflight_artifact_catalog(art, school=self.school)
        self.assertIsNotNone(finding)
        self.assertTrue(any("category" in m.lower() for m in finding["messages"]))

    def test_specialty_catalog_tagged_academics_warns(self):
        art = self._artifact(
            filename="filiere.xlsx",
            domain="academics",
            headers=["NAME", "CODE", "DEPARTMENT"],
            rows=[("ELECTRICAL POWER SYSTEMS", "EPS", "ELECTRICAL")],
        )
        finding = preflight_artifact_catalog(art, school=self.school)
        self.assertIsNotNone(finding)
        self.assertTrue(finding["looks_like_specialty_catalog"])
        self.assertIn("specialties", finding["recommended_domain"])

    def test_correct_tags_are_silent(self):
        subjects = self._artifact(
            filename="subjects.xlsx",
            domain="academics",
            headers=["TITLE", "CATEGORY", "COEF"],
            rows=[("WORKSHOP", "Professional", "4")],
        )
        specs = self._artifact(
            filename="specialties.xlsx",
            domain="specialties",
            headers=["NAME", "CODE", "DEPARTMENT"],
            rows=[("PLUMBING", "PLB", "BUILDING")],
        )
        self.assertIsNone(preflight_artifact_catalog(subjects, school=self.school))
        self.assertIsNone(preflight_artifact_catalog(specs, school=self.school))

    def test_cm_bundle_missing_specialty_file_warns(self):
        self._artifact(
            filename="subjects.xlsx",
            domain="academics",
            headers=["TITLE", "CATEGORY", "COEF"],
            rows=[("WORKSHOP", "Professional", "4")],
        )
        report = assess_bundle_catalog_routing(self.bundle)
        self.assertTrue(report["has_findings"])
        self.assertTrue(any("specialty" in w.lower() or "filière" in w.lower() for w in report["bundle_warnings"]))

    def test_review_notice_and_live_import_surface_warnings(self):
        self._artifact(
            filename="subjects.xlsx",
            domain="specialties",
            headers=["TITLE", "CATEGORY", "COEF"],
            rows=[("WORKSHOP", "Professional", "4")],
        )
        notice = review_notice(self.bundle)
        self.assertIsNotNone(notice)
        self.assertEqual(notice["kind"], "catalog_routing")
        live = compose_live_import(self.bundle, flight={"in_flight": False})
        self.assertIsNotNone(live.get("catalog_routing"))
        self.assertEqual(live["catalog_routing"]["kind"], "catalog_routing")

    def test_artifact_hint_non_empty_on_mismatch(self):
        art = self._artifact(
            filename="subjects.xlsx",
            domain="specialties",
            headers=["TITLE", "CATEGORY", "COEF"],
            rows=[("WORKSHOP", "Professional", "4")],
        )
        hint = artifact_catalog_hint(art, school=self.school)
        self.assertIn("Matières", hint)
