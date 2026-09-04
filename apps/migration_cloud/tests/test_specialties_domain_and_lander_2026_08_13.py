"""Specialties / trades catalog: dedicated domain + lander.

A TVET school's ``specialties`` export (``NAME, CODE, DEPARTMENT`` —
ELECTRICAL POWER SYSTEMS / EPS / ELECTRICAL POWER) previously had no home:
it mis-classified as the subjects catalog (both share name/code/department)
and landed as ``apps.academics.Subject`` rows — the wrong entity.

These tests pin the new ``specialties`` domain end to end: the file
classifies as ``specialties`` (filename breaks the catalog tie against
academics), and the lander creates ``apps.academics.Specialty`` rows plus
their required ``Department``, deduped by (school, name), keeping the source
code when it is globally free.
"""

from __future__ import annotations

import io
import types

from django.test import TestCase

from apps.migration_cloud import artifact_blob_store as store
from apps.migration_cloud.accelerators.runmycampus_canonical import (
    CATALOG_DOMAINS,
    reconcile_domain_with_filename,
)
from apps.migration_cloud.landers.specialty_lander import _clean_department
from apps.migration_cloud.models import (
    ArtifactFormat,
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationBundle,
)
from apps.migration_cloud.ontology.catalog import DOMAINS, all_synonyms


_SPEC_HEADERS = ["﻿NAME", "CODE", "DEPARTMENT"]
_SPEC_ROWS = [
    ["ELECTRICAL POWER SYSTEMS", "EPS", "ELECTRICAL POWER"],
    ["PLUMBING", "PL", "PLUMBING"],
    ["FASHION  DESIGN", "FD", "FASHION  DESIGN - FD"],
    ["BUILDING CONSTRUCTION", "BC", "BUILDING CONSTRUCTION"],
]


class SpecialtiesOntologyTests(TestCase):
    def test_domain_registered(self):
        self.assertIn("specialties", DOMAINS)

    def test_name_synonyms(self):
        syns = {s.lower() for s in all_synonyms("name", domain="specialties")}
        self.assertIn("specialty", syns)
        self.assertIn("filiere", syns)  # fr

    def test_code_and_department_fields(self):
        self.assertTrue(all_synonyms("code", domain="specialties"))
        self.assertIn("department", {s.lower() for s in all_synonyms("department", domain="specialties")})


class CatalogReconcileTests(TestCase):
    def test_specialties_filename_beats_academics_content(self):
        self.assertEqual(
            reconcile_domain_with_filename("specialties_2026.csv", "academics"),
            "specialties",
        )

    def test_subjects_filename_beats_specialties_content(self):
        self.assertEqual(
            reconcile_domain_with_filename("subjects_2026.csv", "specialties"),
            "academics",
        )

    def test_catalog_group_shape(self):
        self.assertEqual(CATALOG_DOMAINS, {"academics", "specialties", "sections"})


class MintScopedCodeUuidTests(TestCase):
    """Seal the cross-cutting bug specialties exposed: ``School.pk`` is a 36-char
    UUID, so the old ``f"{prefix}{sid}-{base}"[:30]`` truncated away the NAME and
    every provisioned Department/Specialty/Classroom code collapsed to ONE value —
    the 2nd..Nth collided on the unique code and quarantined. Affected EVERY code-
    minting lander (structure scaffold, staff, sections), not just specialties."""

    def test_uuid_school_pk_yields_distinct_bounded_codes(self):
        import types
        import uuid

        from apps.academics.models import Department
        from apps.migration_cloud.landers._helpers import mint_scoped_code

        school = types.SimpleNamespace(pk=uuid.uuid4())
        names = [
            "ELECTRICAL POWER", "PLUMBING", "FASHION DESIGN", "BUILDING CONSTRUCTION",
        ]
        codes = [
            mint_scoped_code(prefix="DPT", name=n, school=school, model=Department)
            for n in names
        ]
        self.assertEqual(len(set(codes)), len(names),
                         f"UUID-pk school must yield distinct codes, got {codes}")
        for c in codes:
            self.assertLessEqual(len(c), 30, f"code {c!r} exceeds column max_length")

    def test_short_integer_pk_code_unchanged(self):
        import types

        from apps.academics.models import Department
        from apps.migration_cloud.landers._helpers import mint_scoped_code

        school = types.SimpleNamespace(pk=5)
        self.assertEqual(
            mint_scoped_code(prefix="DPT", name="ELECTRICAL POWER", school=school, model=Department),
            "DPT5-ELECTRIC",
        )


class CleanDepartmentTests(TestCase):
    def test_strips_trailing_source_code(self):
        self.assertEqual(_clean_department("FASHION DESIGN - FD", "FD"), "FASHION DESIGN")

    def test_strips_generic_trailing_code(self):
        self.assertEqual(_clean_department("CARPENTRY AND JOINERY - CJ", ""), "CARPENTRY AND JOINERY")

    def test_leaves_plain_name(self):
        self.assertEqual(_clean_department("ELECTRICAL POWER", "EPS"), "ELECTRICAL POWER")


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


def _make_spec_bundle(school, *, idem: str) -> MigrationBundle:
    data = _xlsx_bytes(_SPEC_HEADERS, _SPEC_ROWS)
    bundle = MigrationBundle.objects.create(
        label="specialties",
        intake_method=IntakeMethod.FILE_UPLOAD,
        idempotency_key=idem,
        status=BundleStatus.INGESTING,
        school=school,
    )
    art = MigrationArtifact.objects.create(
        bundle=bundle,
        path_within_bundle="specialties.xlsx",
        filename="specialties.xlsx",
        detected_format=ArtifactFormat.XLSX,
        byte_size=len(data),
        sha256="0" * 64,
    )
    store.capture_artifact_blob(art, _payload(data))
    return bundle


class SpecialtiesClassifyTests(TestCase):
    def test_specialties_file_classifies_as_specialties(self):
        from apps.migration_cloud.pipeline import advance_bundle

        bundle = _make_spec_bundle(None, idem="spec-classify")
        advance_bundle(bundle_id=bundle.pk, use_accelerator=True)
        bundle.refresh_from_db()
        domain = (
            ((bundle.discovery_summary or {}).get("per_artifact_domain") or {})
            .get("specialties.xlsx", {})
            .get("domain")
        )
        self.assertEqual(domain, "specialties", f"got {domain!r}")


class SpecialtiesApplyTests(TestCase):
    def test_specialties_land_with_departments(self):
        from apps.migration_cloud.orchestrator import apply_bundle
        from apps.migration_cloud.pipeline import advance_bundle
        from apps.academics.models import Department, Specialty
        from apps.schools.models import School

        school = School.objects.create(name="TVET Spec", subdomain="tvet-spec")
        bundle = _make_spec_bundle(school, idem="spec-apply")
        advance_bundle(bundle_id=bundle.pk, use_accelerator=True)
        apply_bundle(bundle_id=bundle.pk, workers=1)

        # Exclude the "General" specialty the post-apply gap-fill (S) ensures as
        # the default FeePlan/SubjectAssignment FK target — this asserts the 4
        # UPLOADED specialties landed, independent of that scaffold.
        specs = Specialty.objects.filter(school=school).exclude(name="General")
        self.assertEqual(specs.count(), 4, "all 4 uploaded specialties should land")
        # Source code kept when globally free.
        self.assertTrue(specs.filter(code="EPS").exists())
        # Department provisioned + the trailing code stripped.
        self.assertTrue(Department.objects.filter(school=school, name="FASHION  DESIGN").exists())

        # Re-apply is idempotent — no duplicate specialties.
        bundle2 = _make_spec_bundle(school, idem="spec-apply-2")
        advance_bundle(bundle_id=bundle2.pk, use_accelerator=True)
        apply_bundle(bundle_id=bundle2.pk, workers=1)
        self.assertEqual(
            Specialty.objects.filter(school=school).exclude(name="General").count(), 4,
            "re-apply must not duplicate specialties",
        )
