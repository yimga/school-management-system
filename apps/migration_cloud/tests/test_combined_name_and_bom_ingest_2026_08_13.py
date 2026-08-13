"""Combined-name (single "Name" column) + BOM-header ingestion.

Real African / French-model SIS exports (e.g. a Cameroonian TVET school)
routinely carry ONE ``Name``/``NAME`` column instead of separate
first/last columns, and a UTF-8 BOM glued to the first CSV/XLSX header.
Before this wave the pipeline:

  * left a BOM-prefixed first header ("﻿NAME") non-ASCII, so it matched
    NO synonym and dumped to ``custom_fields``; and
  * had no ``full_name`` canonical field / ``name`` alias, so a combined
    name never reached the name field and the student lander quarantined
    EVERY row for "missing first/last" (0 of 426 real students landed).

These tests pin the fix end to end: the header normalizes, ``Name`` maps
to the new ``full_name`` canonical field, and the lander splits it into
first/last so the row lands.
"""

from __future__ import annotations

import io
import types

from django.test import TestCase

from apps.migration_cloud import artifact_blob_store as store
from apps.migration_cloud.models import (
    ArtifactFormat,
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationBundle,
)
from apps.migration_cloud.ontology.catalog import all_synonyms
from apps.migration_cloud.profiler import _normalize_header
from apps.migration_cloud.transformers.name_split import split_full_name


class HeaderNormalizationTests(TestCase):
    def test_bom_and_zero_width_stripped_from_header(self):
        # A UTF-8 BOM (U+FEFF) glued to the first header must not survive.
        self.assertEqual(_normalize_header("﻿NAME"), "name")
        self.assertEqual(_normalize_header("﻿title"), "title")
        self.assertEqual(_normalize_header("​Name"), "name")
        # Leading-space header still folds (regression guard).
        self.assertEqual(_normalize_header(" TEACHER UNIQUE ID"), "teacher_unique_id")
        # Non-Latin script is still preserved raw (unchanged behaviour).
        self.assertEqual(_normalize_header("氏名"), "氏名")


class OntologyFullNameTests(TestCase):
    def test_full_name_field_and_name_alias_present(self):
        for domain in ("students", "staff"):
            syns = {s.lower() for s in all_synonyms("full_name", domain=domain)}
            self.assertIn("name", syns, f"{domain}.full_name must alias 'name'")
            self.assertIn("full_name", syns)


class SplitFullNameTests(TestCase):
    def test_first_last(self):
        self.assertEqual(split_full_name("Ada Lovelace"), ("Ada", "", "Lovelace"))

    def test_three_token_middle(self):
        self.assertEqual(
            split_full_name("ACHU DECLAN ANDOH"), ("ACHU", "DECLAN", "ANDOH")
        )

    def test_comma_last_first(self):
        self.assertEqual(split_full_name("Lovelace, Ada"), ("Ada", "", "Lovelace"))

    def test_single_token(self):
        self.assertEqual(split_full_name("Madonna"), ("Madonna", "", ""))

    def test_empty(self):
        self.assertEqual(split_full_name("  "), ("", "", ""))
        self.assertEqual(split_full_name(None), ("", "", ""))


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


class CombinedNameMapsEndToEndTests(TestCase):
    """A students roster with a single ``Name`` column maps it to ``full_name``
    (not ``custom_fields``) through the real profile -> classify -> map path."""

    def test_name_column_maps_to_full_name(self):
        from apps.migration_cloud.pipeline import advance_bundle

        data = _xlsx_bytes(
            ["ID", "Name", "Gender", "Date of Birth"],
            [
                ["247", "ACHU DECLAN ANDOH", "Female", "2012-11-16"],
                ["244", "FAUSTINA MUKU NFOR", "Female", "2012-08-31"],
            ],
        )
        bundle = MigrationBundle.objects.create(
            label="roster",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="combined-name-map",
            status=BundleStatus.INGESTING,
            school=None,
        )
        art = MigrationArtifact.objects.create(
            bundle=bundle,
            path_within_bundle="students.xlsx",
            filename="students.xlsx",
            detected_format=ArtifactFormat.XLSX,
            byte_size=len(data),
            sha256="0" * 64,
        )
        store.capture_artifact_blob(art, _payload(data))

        advance_bundle(bundle_id=bundle.pk, use_accelerator=True)
        bundle.refresh_from_db()

        per_artifact = (bundle.mapping_summary or {}).get("per_artifact") or {}
        mappings = {m["source_column"]: m["canonical_field"]
                    for m in per_artifact.get("students.xlsx", [])}
        self.assertEqual(mappings.get("Name"), "full_name",
                         f"'Name' must map to full_name, got {mappings.get('Name')!r}")
        self.assertEqual(mappings.get("ID"), "external_id")


class SubjectsCatalogClassifiesAsAcademicsTests(TestCase):
    """A subject catalog (title / coef / subject_code / category) must classify
    as ``academics`` (creating Subject rows), NOT ``behavior`` — where every row
    quarantined as an incident 'missing student/date/description'."""

    def test_subjects_file_routes_to_academics_and_maps_title_coef(self):
        from apps.migration_cloud.pipeline import advance_bundle

        data = _xlsx_bytes(
            ["title", "fr_title", "coef", "subject_code", "category"],
            [
                ["WORKSHOP PRACTICE", "ATELIER", "6", "WP", "Professional"],
                ["MATHEMATICS", "Mathematiques", "03", "MATH", "General"],
            ],
        )
        bundle = MigrationBundle.objects.create(
            label="subjects",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="subjects-academics-map",
            status=BundleStatus.INGESTING,
            school=None,
        )
        art = MigrationArtifact.objects.create(
            bundle=bundle,
            path_within_bundle="subjects.xlsx",
            filename="subjects.xlsx",
            detected_format=ArtifactFormat.XLSX,
            byte_size=len(data),
            sha256="0" * 64,
        )
        store.capture_artifact_blob(art, _payload(data))

        advance_bundle(bundle_id=bundle.pk, use_accelerator=True)
        bundle.refresh_from_db()

        domain = ((bundle.discovery_summary or {}).get("per_artifact_domain") or {}).get(
            "subjects.xlsx", {}
        ).get("domain")
        self.assertEqual(domain, "academics",
                         f"subjects catalog must classify as academics, got {domain!r}")
        per_artifact = (bundle.mapping_summary or {}).get("per_artifact") or {}
        mappings = {m["source_column"]: m["canonical_field"]
                    for m in per_artifact.get("subjects.xlsx", [])}
        self.assertEqual(mappings.get("title"), "subject_name")
        self.assertEqual(mappings.get("coef"), "credits")
